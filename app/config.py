from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Feishu / Lark
    FEISHU_APP_ID: str = Field(description="飞书应用 App ID")
    FEISHU_APP_SECRET: str = Field(description="飞书应用 App Secret")
    FEISHU_VERIFICATION_TOKEN: str = Field(description="飞书事件订阅 Verification Token")
    FEISHU_ENCRYPT_KEY: str = Field(description="飞书事件加密 Encrypt Key (AES-256-CBC)")
    FEISHU_DOMAIN: str = Field(default="https://open.feishu.cn", description="飞书 OpenAPI 域名")

    # Doubao / ByteDance Ark LLM
    DOUBAO_API_KEY: str = Field(description="豆包 Ark API Key")
    DOUBAO_BASE_URL: str = Field(description="豆包 Ark API Base URL, 不带末尾 /v1")
    DOUBAO_MODEL_PRO: str = Field(description="豆包 Pro 端点 ID, e.g. ep-20241230xxxxx")
    DOUBAO_MODEL_LITE: str = Field(description="豆包 Lite 端点 ID, 用于低成本任务")

    # Volcano Engine ASR
    VOLC_ASR_APP_ID: str = Field(description="火山引擎语音识别 App ID")
    VOLC_ASR_ACCESS_TOKEN: str = Field(description="火山引擎 ASR Access Token")
    VOLC_ASR_CLUSTER: str = Field(
        default="volcengine_input_common", description="火山引擎 ASR 集群 ID"
    )

    # PostgreSQL (async via psycopg3 asyncio)
    DATABASE_URL: str = Field(
        description="异步数据库连接串, e.g. postgresql+psycopg://forge:pass@localhost:5432/forge"
    )
    # Sync URL for Alembic migrations (psycopg3 sync driver)
    DATABASE_URL_SYNC: str = Field(
        description="同步数据库连接串供 Alembic 使用, e.g. postgresql+psycopg://forge:pass@localhost:5432/forge"
    )

    # Redis
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0", description="Redis 连接串, Celery broker + backend"
    )

    # ChromaDB
    CHROMA_HOST: str = Field(default="localhost", description="ChromaDB 服务主机")
    CHROMA_PORT: int = Field(default=8001, description="ChromaDB 服务端口")
    CHROMA_TENANT: str = Field(default="default_tenant", description="ChromaDB tenant 名")
    CHROMA_COLLECTION_NAME: str = Field(default="forge_kb", description="ChromaDB 默认集合名称")

    # Embedding model cache (bge-base-zh-v1.5)
    MODEL_CACHE_DIR: str = Field(
        default="~/.cache/forge/models",
        description="Embedding 模型缓存目录",
    )

    # LangSmith tracing (optional)
    LANGSMITH_API_KEY: str = Field(
        default="", description="LangSmith API key, 空字符串关闭 tracing"
    )
    LANGSMITH_PROJECT: str = Field(default="forge-dev", description="LangSmith project 名称")
    LANGSMITH_TRACING: bool = Field(default=False, description="LangSmith tracing 总开关")

    # Stage 2 graph rollout flag
    FORGE_USE_GRAPH: bool = Field(
        default=False,
        description="True 时 message_tasks 走 LangGraph; False 沿用 Stage 1 直调路径",
    )

    # Application
    APP_ENV: str = Field(default="dev", description="运行环境: dev | staging | prod")
    LOG_LEVEL: str = Field(default="INFO", description="日志级别: DEBUG | INFO | WARNING | ERROR")
    API_HOST: str = Field(default="0.0.0.0", description="FastAPI 监听地址")
    API_PORT: int = Field(default=8000, description="FastAPI 监听端口")

    # Celery
    CELERY_TASK_TIME_LIMIT: int = Field(default=180, description="任务硬超时秒数")
    CELERY_TASK_SOFT_TIME_LIMIT: int = Field(default=150, description="任务软超时秒数")
    CELERY_WORKER_CONCURRENCY: int = Field(default=4, description="Celery Worker 并发数")

    # Feature stage
    FORGE_STAGE: int = Field(default=2, description="当前功能阶段：2=doc only，3=doc+ppt")


@lru_cache
def get_settings() -> Settings:
    return Settings()
