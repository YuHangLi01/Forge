"""Load a slide outline JSON fixture into a list of SlideSchema.

The fixture format (see tests/fixtures/outlines/*.json):

    {
      "title": "...",
      "subtitle": "...",
      "slides": [
        {"type": "title|content", "title": "...", "subtitle": "...", "bullets": [...]}
      ]
    }

This loader is the bridge between the human-authored outline file (or
LLM-produced JSON) and `PPTService.create_from_outline`.
"""

import json
from pathlib import Path
from typing import Any

from app.schemas.artifacts import SlideSchema
from app.schemas.enums import SlideLayout


def load_outline(path: Path | str) -> tuple[str, str, list[SlideSchema]]:
    """Read a fixture and return (title, subtitle, slides).

    Raises ValueError if the JSON shape is wrong. Caller is expected to
    propagate; downstream `PPTService` doesn't second-guess the outline.
    """
    raw = Path(path).read_text(encoding="utf-8")
    obj: dict[str, Any] = json.loads(raw)
    title = str(obj.get("title", ""))
    subtitle = str(obj.get("subtitle", ""))
    raw_slides = obj.get("slides", [])
    if not isinstance(raw_slides, list):
        raise ValueError(f"{path}: 'slides' must be a list")

    slides: list[SlideSchema] = []
    for idx, item in enumerate(raw_slides):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: slide #{idx} is not an object")
        layout = _layout_from_type(item.get("type", "content"))
        bullets = item.get("bullets", []) or []
        if item.get("type") == "title" and item.get("subtitle"):
            # Cover layout uses bullets[0] as subtitle (see PptxBuilder)
            bullets = [str(item["subtitle"])]
        slides.append(
            SlideSchema(
                page_index=idx,
                layout=layout,
                title=str(item.get("title", "")),
                bullets=[str(b) for b in bullets],
            )
        )

    return title, subtitle, slides


def _layout_from_type(kind: str) -> SlideLayout:
    if kind == "title":
        return SlideLayout.cover
    if kind == "section":
        return SlideLayout.section_header
    if kind == "two_column":
        return SlideLayout.two_column
    if kind == "blank":
        return SlideLayout.blank
    return SlideLayout.title_content
