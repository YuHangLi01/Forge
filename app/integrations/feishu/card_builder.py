from typing import Any


class CardBuilder:
    """Fluent builder for Feishu Interactive Card v2 JSON."""

    def __init__(self) -> None:
        self._header: dict[str, Any] | None = None
        self._elements: list[dict[str, Any]] = []

    def header(self, title: str, template: str = "blue") -> "CardBuilder":
        self._header = {
            "title": {"tag": "plain_text", "content": title},
            "template": template,
        }
        return self

    def text(self, content: str, tag: str = "lark_md") -> "CardBuilder":
        self._elements.append(
            {
                "tag": "div",
                "text": {"tag": tag, "content": content},
            }
        )
        return self

    def divider(self) -> "CardBuilder":
        self._elements.append({"tag": "hr"})
        return self

    def note(self, content: str) -> "CardBuilder":
        self._elements.append(
            {
                "tag": "note",
                "elements": [{"tag": "lark_md", "content": content}],
            }
        )
        return self

    def actions(self, buttons: list[dict[str, str]]) -> "CardBuilder":
        actions_list = []
        for btn in buttons:
            actions_list.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": btn.get("text", "")},
                    "type": btn.get("type", "default"),
                    "value": {"action": btn.get("action", "")},
                }
            )
        self._elements.append({"tag": "action", "actions": actions_list})
        return self

    def progress(self, current: int, total: int) -> "CardBuilder":
        bar_len = 20
        filled = int(bar_len * current / max(total, 1))
        bar = "█" * filled + "░" * (bar_len - filled)
        self._elements.append(
            {
                "tag": "div",
                "text": {"tag": "plain_text", "content": f"进度 {bar} {current}/{total}"},
            }
        )
        return self

    def build(self) -> dict[str, Any]:
        card: dict[str, Any] = {
            "schema": "2.0",
            "body": {"elements": self._elements},
        }
        if self._header:
            card["header"] = self._header
        return card
