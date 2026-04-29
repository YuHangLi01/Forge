from app.exceptions import FeishuAPIError, FeishuRateLimitError

__all__ = ["FeishuAPIError", "FeishuRateLimitError", "FeishuAuthError"]


class FeishuAuthError(FeishuAPIError):
    """Feishu app authentication failed (invalid app_id / app_secret)."""
