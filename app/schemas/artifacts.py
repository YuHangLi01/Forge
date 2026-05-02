from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import ChartType, SlideLayout


class DocSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    content_md: str
    block_ids: list[str] = Field(default_factory=list, description="写入飞书后回填的 block_id 列表")


class DocArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str = Field(description="飞书 doc_token")
    title: str
    sections: list[DocSection] = Field(default_factory=list)
    share_url: str = ""


class ChartSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    values: list[float]


class ChartSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chart_type: ChartType = ChartType.bar
    title: str = ""
    categories: list[str] = Field(default_factory=list)
    series: list[ChartSeries] = Field(default_factory=list)


class SlideSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_index: int = Field(ge=0)
    layout: SlideLayout = SlideLayout.title_content
    title: str
    bullets: list[str] = Field(default_factory=list)
    visual_hint: str | None = None
    speaker_notes: str = ""
    element_ids: dict[str, str] = Field(
        default_factory=dict, description="逻辑名 → 飞书 element_id"
    )
    chart: ChartSchema | None = None


class PPTArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ppt_id: str = Field(description="飞书 ppt_token 或云盘 file_token")
    title: str
    slides: list[SlideSchema] = Field(default_factory=list)
    share_url: str = ""
