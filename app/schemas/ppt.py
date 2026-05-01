"""PPT generation schemas: brief → slides."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PageType = Literal["cover", "agenda", "section_header", "content", "closing"]


class SlideBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slide_index: int = Field(ge=0, description="幻灯片序号，从 0 开始")
    page_type: PageType = Field(description="幻灯片类型")
    title: str = Field(description="幻灯片标题，≤30 字")
    bullet_points: list[str] = Field(
        default_factory=list,
        description="要点列表，每条 ≤50 字，content 页 3-6 条，其他页 0-2 条",
    )
    speaker_notes: str = Field(
        default="",
        description="演讲者备注，≤150 字",
    )


class PPTBriefSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="整份 PPT 标题")
    target_audience: str = Field(description="目标受众描述，用于选择 design token")
    slides: list[SlideBrief] = Field(description="幻灯片列表，3-20 页")
    design_token_name: str = Field(
        default="",
        description="design token 预设名称（留空由系统自动选择）",
    )

    @property
    def slide_count(self) -> int:
        return len(self.slides)
