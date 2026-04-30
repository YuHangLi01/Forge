from pydantic import BaseModel, ConfigDict, Field


class ModificationRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    step_index: int = Field(ge=0, description="Which modification this was (0-based)")
    scope_identifier: str = Field(description="Section title or block_id that was edited")
    instruction: str = Field(description="Original user instruction that triggered the edit")
    before_summary: str = Field(max_length=200, description="≤200-char summary of content before")
    after_summary: str = Field(max_length=200, description="≤200-char summary of content after")
