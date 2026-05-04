from __future__ import annotations

from pydantic import BaseModel


class ReplanDecision(BaseModel):
    should_add: bool
    slide_title: str = ""
    bullet_points: list[str] = []
