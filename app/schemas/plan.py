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
        # completed contains node_names (e.g. "doc_structure_gen"), not step ids.
        # depends_on contains step ids — resolve them to node_names for the check.
        id_to_node = {s.id: s.node_name for s in self.steps}
        for step in self.steps:
            if step.node_name in completed:
                continue
            if all(id_to_node.get(dep, dep) in completed for dep in step.depends_on):
                return step
        return None
