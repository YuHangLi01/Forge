from app.integrations.feishu.exceptions import FeishuAuthError
from app.integrations.feishu.models import FeishuFileDTO, FeishuMessageDTO, FeishuUserDTO


def test_feishu_message_dto() -> None:
    msg = FeishuMessageDTO(
        message_id="m1",
        chat_id="c1",
        sender_user_id="u1",
        message_type="text",
        content='{"text":"hello"}',
    )
    assert msg.message_id == "m1"
    assert msg.message_type == "text"


def test_feishu_user_dto_defaults() -> None:
    user = FeishuUserDTO(user_id="u1", name="Alice")
    assert user.avatar_url == ""


def test_feishu_file_dto() -> None:
    f = FeishuFileDTO(file_token="tok1", file_name="report.pptx")
    assert f.file_size == 0
    assert f.share_url == ""


def test_feishu_auth_error_hierarchy() -> None:
    from app.exceptions import FeishuAPIError, ForgeError

    err = FeishuAuthError("auth failed", feishu_code=99991401)
    assert isinstance(err, FeishuAPIError)
    assert isinstance(err, ForgeError)
    assert err.feishu_code == 99991401
