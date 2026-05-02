from enum import StrEnum


class TaskStatus(StrEnum):
    pending = "pending"
    running = "running"
    waiting_human = "waiting_human"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class TaskType(StrEnum):
    create_new = "create_new"
    modify_existing = "modify_existing"
    query_only = "query_only"


class OutputFormat(StrEnum):
    document = "document"
    presentation = "presentation"
    message_only = "message_only"


class ScopeType(StrEnum):
    full = "full"
    specific_section = "specific_section"
    specific_slide = "specific_slide"
    specific_block = "specific_block"


class ModificationType(StrEnum):
    rewrite = "rewrite"
    reformat = "reformat"
    append = "append"
    delete = "delete"


class SlideLayout(StrEnum):
    cover = "cover"
    title_content = "title_content"
    two_column = "two_column"
    blank = "blank"
    section_header = "section_header"


class ChartType(StrEnum):
    bar = "bar"
    line = "line"
    pie = "pie"
