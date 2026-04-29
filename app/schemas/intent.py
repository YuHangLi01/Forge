from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import ModificationType, OutputFormat, ScopeType, TaskType


class IntentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: TaskType
    primary_goal: str = Field(..., description="一句话目标,用于 RAG query")
    output_formats: list[OutputFormat]
    target_audience: str | None = None
    style_hint: str | None = None
    ambiguity_score: float = Field(ge=0.0, le=1.0, description="意图模糊程度 0=清晰 1=完全模糊")
    missing_info: list[str] = Field(default_factory=list, description="缺失信息列表")


class ModificationIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: OutputFormat
    scope_type: ScopeType
    scope_identifier: str = Field(..., description="范围标识符, e.g. '第三页' / block_id")
    modification_type: ModificationType
    instruction: str = Field(..., description="具体修改指令")
