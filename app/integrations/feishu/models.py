from pydantic import BaseModel, ConfigDict


class FeishuMessageDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message_id: str
    chat_id: str
    sender_user_id: str
    message_type: str
    content: str


class FeishuUserDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_id: str
    name: str
    avatar_url: str = ""


class FeishuFileDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    file_token: str
    file_name: str
    file_size: int = 0
    share_url: str = ""
