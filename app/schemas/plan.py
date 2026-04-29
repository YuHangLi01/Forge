from pydantic import BaseModel, ConfigDict, Field


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    node_name: str
    depends_on: list[str] = Field(default_factory=list)
    requires_human_confirm: bool = False
    estimated_seconds: int = Field(default=30, ge=0)


class PlanSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[PlanStep]
    total_estimated_seconds: int = Field(default=0, ge=0)

    def next_runnable_step(self, completed: set[str]) -> PlanStep | None:
        for step in self.steps:
            if step.id in completed:
                continue
            if all(dep in completed for dep in step.depends_on):
                return step
        return None
