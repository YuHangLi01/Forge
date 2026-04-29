"""Feishu Doc API block type constants."""

PAGE = 1
TEXT = 2
HEADING1 = 3
HEADING2 = 4
HEADING3 = 5
HEADING4 = 6
HEADING5 = 7
HEADING6 = 8
HEADING7 = 9
BULLET = 12
ORDERED = 13
CODE = 14
QUOTE = 15
TODO = 17
DIVIDER = 22
TABLE = 31
GRID = 40

HEADING_LEVEL_MAP = {1: HEADING1, 2: HEADING2, 3: HEADING3}

CODE_LANG_MAP = {
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "java": "Java",
    "go": "Go",
    "rust": "Rust",
    "bash": "Shell",
    "sh": "Shell",
    "sql": "SQL",
    "json": "JSON",
    "yaml": "YAML",
    "xml": "XML",
    "html": "HTML",
    "css": "CSS",
    "": "PlainText",
}
