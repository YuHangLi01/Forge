"""Demo task: produce a sample meeting Doc + matching .pptx and reply with links.

Triggered when the user asks the bot to "生成PPT" / "生成文档" / "demo" etc.
(see ``app.services.intent_router``).

The task is intentionally deterministic and offline-safe:
- Fixture choice is pseudo-random but driven by the message_id hash, so the
  same incoming message always yields the same fixture (helps debugging).
- All five fixtures live under ``tests/fixtures/{meetings,outlines}``; the
  fixture set ships with the repo so this works without any LLM call.
- Doc creation goes through ``FeishuDocService`` (live Feishu API);
  PPT goes through ``PPTService`` (offline build) → ``upload_drive_file``.

If anything goes wrong (network, scope, quota), the user gets an apology
reply rather than silence — the operator decides next step from logs.
"""

import asyncio
import hashlib
from pathlib import Path
from typing import Any

import structlog

from app.tasks.base import forge_task

logger = structlog.get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MEETINGS_DIR = _REPO_ROOT / "tests" / "fixtures" / "meetings"
_OUTLINES_DIR = _REPO_ROOT / "tests" / "fixtures" / "outlines"

_FIXTURE_NAMES: tuple[str, ...] = (
    "01_requirements",
    "02_granularity",
    "03_midterm_review",
    "04_project_pr",
    "05_defense",
)

_FIXTURE_TITLES: dict[str, str] = {
    "01_requirements": "需求确定会会议纪要",
    "02_granularity": "颗粒度对齐会会议纪要",
    "03_midterm_review": "中期验收会会议纪要",
    "04_project_pr": "项目公关会会议纪要",
    "05_defense": "答辩会会议纪要",
}


def pick_fixture(seed: str) -> str:
    """Map a stable string (e.g. message_id) to one of the 5 fixtures."""
    h = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16)
    return _FIXTURE_NAMES[h % len(_FIXTURE_NAMES)]


@forge_task(name="forge.handle_demo_request", queue="slow")  # type: ignore[untyped-decorator]
def handle_demo_request_task(self: Any, payload: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    return asyncio.run(_handle_demo_async(payload))


async def _handle_demo_async(payload: dict[str, Any]) -> dict[str, Any]:
    from app.integrations.feishu.adapter import FeishuAdapter
    from app.services.message_router import parse_message

    msg = parse_message(payload)
    feishu = FeishuAdapter()
    fixture = pick_fixture(msg.message_id or msg.event_id or "fallback")
    title_zh = _FIXTURE_TITLES[fixture]

    logger.info("demo_started", fixture=fixture, message_id=msg.message_id)

    if msg.message_id:
        try:
            await feishu.reply_text(
                msg.message_id,
                f"📄 正在生成示例「{title_zh}」+ 配套 PPT，约 20 秒…",
            )
        except Exception:
            logger.warning("demo_pre_reply_failed", message_id=msg.message_id)

    try:
        result = await _build_demo(feishu, fixture, title_zh)
    except Exception as exc:
        logger.exception("demo_failed", fixture=fixture, error=str(exc))
        try:
            await feishu.reply_text(
                msg.message_id,
                f"❌ 生成示例失败：{exc}\n请联系运维查看 forge-worker 日志。",
            )
        except Exception:
            logger.exception("demo_error_reply_failed")
        return {"status": "error", "error": str(exc)}

    reply_text = (
        "✅ 示例生成完成：\n\n"
        f"📄 会议纪要：{result['doc_share_url']}\n"
        f"📊 配套 PPT：{result['pptx_share_url']}"
    )
    if msg.message_id:
        await feishu.reply_text(msg.message_id, reply_text)
    return {"status": "completed", **result}


async def _build_demo(feishu: Any, fixture: str, title_zh: str) -> dict[str, str]:
    from app.services.feishu_doc_service import FeishuDocService
    from app.services.ppt_outline_loader import load_outline
    from app.services.ppt_service import PPTService

    md_path = _MEETINGS_DIR / f"{fixture}.md"
    outline_path = _OUTLINES_DIR / f"{fixture}.json"
    if not md_path.exists() or not outline_path.exists():
        raise FileNotFoundError(f"missing fixture files for {fixture}")

    markdown = md_path.read_text(encoding="utf-8")
    outline_title, subtitle, slides = load_outline(outline_path)

    # 1. Doc — use the simple converter for known-good schema compliance
    doc_artifact = await FeishuDocService(feishu).create_from_markdown(
        title=f"[Forge demo] {title_zh}",
        markdown=markdown,
        simple=True,
    )

    # 2. PPT bytes
    pptx_bytes = await PPTService().build_pptx_bytes(outline_title, slides, subtitle=subtitle)

    # 3. Upload PPT to Drive
    file_token = await feishu.upload_drive_file(
        name=f"{fixture}.pptx",
        content=pptx_bytes,
    )
    pptx_share_url = await feishu.get_share_url(file_token, type_="file")

    logger.info(
        "demo_finished",
        fixture=fixture,
        doc_token=doc_artifact.doc_id,
        pptx_token=file_token,
        bytes_len=len(pptx_bytes),
    )
    return {
        "fixture": fixture,
        "doc_token": doc_artifact.doc_id,
        "doc_share_url": doc_artifact.share_url,
        "pptx_token": file_token,
        "pptx_share_url": pptx_share_url,
    }
