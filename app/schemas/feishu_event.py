from pydantic import BaseModel, ConfigDict, Field


class FeishuSenderId(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_id: str = ""
    open_id: str = ""
    union_id: str = ""


class FeishuSender(BaseModel):
    model_config = ConfigDict(extra="allow")

    sender_id: FeishuSenderId = Field(default_factory=FeishuSenderId)
    sender_type: str = ""


class FeishuMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    message_id: str = ""
    root_id: str = ""
    parent_id: str = ""
    message_type: str = ""
    chat_id: str = ""
    chat_type: str = ""
    content: str = Field(default="{}", description="JSON 字符串,按 message_type 解析")


class FeishuEventBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    sender: FeishuSender = Field(default_factory=FeishuSender)
    message: FeishuMessage = Field(default_factory=FeishuMessage)


class FeishuEventHeader(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str = ""
    event_type: str = ""
    create_time: str = ""
    token: str = ""
    app_id: str = ""
    tenant_key: str = ""


class FeishuWebhookPayload(BaseModel):
    """飞书 Webhook 事件 Payload (Schema v2.0)."""

    model_config = ConfigDict(extra="allow")

    schema_version: str = Field(default="2.0", alias="schema")
    header: FeishuEventHeader = Field(default_factory=FeishuEventHeader)
    event: FeishuEventBody | None = None
    # URL verification fields
    challenge: str | None = None
    token: str | None = None
    type: str | None = None
