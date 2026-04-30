from pydantic import BaseModel, ConfigDict, Field


class DocOutlineSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str


class DocOutline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_title: str
    sections: list[DocOutlineSection] = Field(min_length=1)
