"""Lego scenario codes for multi-format orchestration."""

from __future__ import annotations

from enum import StrEnum


class LegoScenario(StrEnum):
    C = "C"  # Create document: doc_structure_gen → doc_content_gen → feishu_doc_write
    D = "D"  # Create PPT: ppt_structure_gen → ppt_content_gen → feishu_ppt_write
    # F reserved for future expansion
