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

# Feishu code-block language enum (int).
# Reference: https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/data-structure/block#code
# Values are the documented integer codes; PlainText (1) is used as the
# default fallback when the markdown fence info is missing or unknown.
CODE_LANG_PLAIN = 1
CODE_LANG_MAP = {
    "python": 49,
    "javascript": 30,
    "js": 30,
    "typescript": 63,
    "ts": 63,
    "java": 28,
    "go": 22,
    "rust": 51,
    "bash": 4,
    "sh": 4,
    "shell": 4,
    "sql": 54,
    "json": 31,
    "yaml": 65,
    "yml": 65,
    "xml": 64,
    "html": 24,
    "css": 12,
    "": CODE_LANG_PLAIN,
}
