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

    # Volcano Engine ASR (录音文件转写 v3)
    VOLC_ASR_APP_ID: str = Field(description="火山引擎 ASR App ID（旧版控制台 X-Api-App-Key）")
    VOLC_ASR_ACCESS_TOKEN: str = Field(
        description="火山引擎 ASR Access Token（旧版控制台 X-Api-Access-Key）"
    )
    VOLC_ASR_RESOURCE_ID: str = Field(
        default="volc.bigasr.auc",
        description="火山引擎 ASR Resource ID；v2.0 用 volc.seedasr.auc，v1.0 用 volc.bigasr.auc",
    )
    VOLC_ASR_CLUSTER: str = Field(
        default="volcengine_input_common", description="火山引擎 ASR 集群 ID（v1 遗留，v3 不使用）"
    )

    # Forge public URL — Volcengine ASR v3 需要从公网拉取音频文件
    FORGE_PUBLIC_URL: str = Field(
        default="",
        description=(
            "Forge 服务对公网可达的 Base URL，不带末尾 /，"
            "例如 https://forge.example.com。"
            "火山引擎 ASR v3 录音文件转写会从此地址下载临时音频，必须填写。"
        ),
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
    LANGSMITH_HIDE_INPUTS: bool = Field(
        default=True, description="LangSmith tracing 时隐藏输入内容（PII 保护）"
    )

    # Graph rollout flag
    FORGE_USE_GRAPH: bool = Field(
        default=True,
        description="True 时 message_tasks 走 LangGraph; False 沿用 Stage 1 直调路径",
    )

    # Application
    APP_ENV: str = Field(default="dev", description="运行环境: dev | staging | prod")
    LOG_LEVEL: str = Field(default="INFO", description="日志级别: DEBUG | INFO | WARNING | ERROR")
    API_HOST: str = Field(default="0.0.0.0", description="FastAPI 监听地址")
    API_PORT: int = Field(default=8000, description="FastAPI 监听端口")

    # Celery
    CELERY_TASK_TIME_LIMIT: int = Field(default=360, description="任务硬超时秒数")
    CELERY_TASK_SOFT_TIME_LIMIT: int = Field(default=300, description="任务软超时秒数")
    CELERY_WORKER_CONCURRENCY: int = Field(default=4, description="Celery Worker 并发数")

    # Feishu Wiki (knowledge base archival)
    FEISHU_WIKI_SPACE_ID: str = Field(
        default="",
        description="飞书知识库 Space ID，用于归档任务产物（留空则跳过归档）",
    )
    FEISHU_WIKI_PARENT_NODE_TOKEN: str = Field(
        default="",
        description="飞书知识库父节点 Token，新归档节点挂在此节点下（留空则挂根节点）",
    )

    # Feature stage
    FORGE_STAGE: int = Field(default=3, description="当前功能阶段：2=doc only，3=doc+ppt")


@lru_cache
def get_settings() -> Settings:
    return Settings()
