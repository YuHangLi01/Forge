"""Design token system for PPT generation.

Five fixed presets are selected by target_audience so the LLM never
outputs raw style parameters.  Routing is done in Python, not via LLM.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DesignToken:
    name: str
    primary_color: str
    secondary_color: str
    background_color: str
    text_color: str
    accent_color: str
    font_title: str
    font_body: str
    font_size_title: int
    font_size_body: int
    font_size_caption: int


_PRESETS: dict[str, DesignToken] = {
    "corporate": DesignToken(
        name="corporate",
        primary_color="#1B3A6B",
        secondary_color="#2E5FA3",
        background_color="#FFFFFF",
        text_color="#1A1A1A",
        accent_color="#E8861A",
        font_title="方正黑体",
        font_body="方正宋体",
        font_size_title=36,
        font_size_body=18,
        font_size_caption=14,
    ),
    "tech_dark": DesignToken(
        name="tech_dark",
        primary_color="#00D4FF",
        secondary_color="#7B2FFF",
        background_color="#0D0D1A",
        text_color="#E8E8F0",
        accent_color="#FF6B35",
        font_title="Source Han Sans",
        font_body="Source Han Sans",
        font_size_title=38,
        font_size_body=18,
        font_size_caption=13,
    ),
    "warm_narrative": DesignToken(
        name="warm_narrative",
        primary_color="#C0392B",
        secondary_color="#E67E22",
        background_color="#FDF6EC",
        text_color="#2C2C2C",
        accent_color="#27AE60",
        font_title="方正楷体",
        font_body="方正宋体",
        font_size_title=34,
        font_size_body=19,
        font_size_caption=14,
    ),
    "minimal": DesignToken(
        name="minimal",
        primary_color="#222222",
        secondary_color="#555555",
        background_color="#FAFAFA",
        text_color="#222222",
        accent_color="#0066CC",
        font_title="PingFang SC",
        font_body="PingFang SC",
        font_size_title=36,
        font_size_body=17,
        font_size_caption=13,
    ),
    "data_driven": DesignToken(
        name="data_driven",
        primary_color="#00897B",
        secondary_color="#0277BD",
        background_color="#F5F9FF",
        text_color="#1A2535",
        accent_color="#F57C00",
        font_title="方正黑体",
        font_body="方正黑体",
        font_size_title=32,
        font_size_body=17,
        font_size_caption=12,
    ),
}

# audience keyword → preset name
_AUDIENCE_MAP: list[tuple[tuple[str, ...], str]] = [
    (
        (
            "投资",
            "investor",
            "融资",
            "vc",
            "基金",
            "路演",
            "vp",
            "高管",
            "领导",
            "executive",
            "管理层",
            "总裁",
            "ceo",
            "董事",
            "汇报",
            "述职",
            "季度",
        ),
        "corporate",
    ),
    (("技术", "tech", "研发", "developer", "工程", "架构"), "tech_dark"),
    (("故事", "narrative", "情感", "文化", "宣传", "品牌"), "warm_narrative"),
    (("数据", "data", "分析", "report", "运营", "指标", "dashboard"), "data_driven"),
]

_DEFAULT_PRESET = "minimal"


def resolve_token(target_audience: str) -> DesignToken:
    """Return the best-matching DesignToken for the given audience description."""
    audience_lower = target_audience.lower()
    for keywords, preset_name in _AUDIENCE_MAP:
        if any(kw in audience_lower for kw in keywords):
            return _PRESETS[preset_name]
    return _PRESETS[_DEFAULT_PRESET]


def get_preset(name: str) -> DesignToken:
    """Return a preset by exact name.  Raises KeyError for unknown names."""
    return _PRESETS[name]


def list_presets() -> list[str]:
    return list(_PRESETS.keys())
