from app.integrations.feishu.card_builder import CardBuilder


def test_build_minimal_card() -> None:
    card = CardBuilder().build()
    assert card["schema"] == "2.0"
    assert "body" in card
    assert card["body"]["elements"] == []


def test_card_with_header() -> None:
    card = CardBuilder().header(title="Test Title", template="green").build()
    assert card["header"]["title"]["content"] == "Test Title"
    assert card["header"]["template"] == "green"


def test_card_with_text() -> None:
    card = CardBuilder().text("Hello, **world**").build()
    assert card["body"]["elements"][0]["tag"] == "div"
    assert card["body"]["elements"][0]["text"]["content"] == "Hello, **world**"


def test_card_with_divider() -> None:
    card = CardBuilder().divider().build()
    assert card["body"]["elements"][0]["tag"] == "hr"


def test_card_with_note() -> None:
    card = CardBuilder().note("Some note").build()
    el = card["body"]["elements"][0]
    assert el["tag"] == "note"
    assert el["elements"][0]["content"] == "Some note"


def test_card_with_actions() -> None:
    card = (
        CardBuilder()
        .actions(
            [
                {"text": "Confirm", "action": "confirm", "type": "primary"},
                {"text": "Cancel", "action": "cancel"},
            ]
        )
        .build()
    )
    action_el = card["body"]["elements"][0]
    assert action_el["tag"] == "action"
    assert len(action_el["actions"]) == 2
    assert action_el["actions"][0]["type"] == "primary"
    assert action_el["actions"][0]["value"]["action"] == "confirm"


def test_card_with_progress() -> None:
    card = CardBuilder().progress(current=3, total=6).build()
    el = card["body"]["elements"][0]
    assert "3/6" in el["text"]["content"]


def test_card_fluent_chain() -> None:
    card = (
        CardBuilder()
        .header(title="Status", template="blue")
        .text("Processing...")
        .divider()
        .progress(current=1, total=4)
        .actions([{"text": "Cancel", "action": "cancel"}])
        .note("Last updated now")
        .build()
    )
    assert len(card["body"]["elements"]) == 5
    assert card["header"]["title"]["content"] == "Status"


def test_card_no_header_no_key() -> None:
    card = CardBuilder().text("hi").build()
    assert "header" not in card


def test_progress_zero_total() -> None:
    card = CardBuilder().progress(current=0, total=0).build()
    el = card["body"]["elements"][0]
    assert "0/0" in el["text"]["content"]
