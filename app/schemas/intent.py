from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.enums import ModificationType, OutputFormat, ScopeType, TaskType

# LLM 有时会输出不在枚举里的近义词，在 Pydantic 校验前归一化
_SCOPE_TYPE_ALIASES: dict[str, str] = {
    "page": "specific_slide",
    "specific_page": "specific_slide",
    "slide": "specific_slide",
    "section": "specific_section",
    "block": "specific_block",
    "paragraph": "specific_block",
    "all": "full",
    "whole": "full",
    "entire": "full",
}

_MODIFICATION_TYPE_ALIASES: dict[str, str] = {
    "add_chart": "append",
    "add_image": "append",
    "add_element": "append",
    "add_content": "append",
    "add": "append",
    "insert": "append",
    "replace": "rewrite",
    "update": "rewrite",
    "modify": "rewrite",
    "edit": "rewrite",
    "revise": "rewrite",
    "format": "reformat",
    "style": "reformat",
    "remove": "delete",
    "erase": "delete",
}


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
    ambiguity_high: bool = Field(default=False, description="是否需要用户确认修改对象")

    @field_validator("scope_type", mode="before")
    @classmethod
    def normalize_scope_type(cls, v: object) -> object:
        if not isinstance(v, str):
            return v
        normalized = _SCOPE_TYPE_ALIASES.get(v.lower(), v)
        if normalized == v:
            lower = v.lower()
            if any(kw in lower for kw in ("全文", "整体", "全部", "所有", "整个")):
                return "full"
            if any(kw in lower for kw in ("页", "幻灯片", "slide")):
                return "specific_slide"
            if any(kw in lower for kw in ("节", "章", "段落", "部分")):
                return "specific_section"
        return normalized

    @field_validator("modification_type", mode="before")
    @classmethod
    def normalize_modification_type(cls, v: object) -> object:
        if not isinstance(v, str):
            return v
        normalized = _MODIFICATION_TYPE_ALIASES.get(v.lower(), v)
        if normalized == v:
            lower = v.lower()
            _reformat_kws = (
                "格式",
                "排版",
                "尺寸",
                "样式",
                "字体",
                "颜色",
                "布局",
                "对齐",
                "缩小",
                "放大",
                "调整",
            )
            if any(kw in lower for kw in _reformat_kws):
                return "reformat"
            if any(kw in lower for kw in ("删除", "移除", "清除", "去掉", "取消")):
                return "delete"
            if any(kw in lower for kw in ("增加", "添加", "插入", "新增", "加上", "补充")):
                return "append"
            return "rewrite"
        return normalized
