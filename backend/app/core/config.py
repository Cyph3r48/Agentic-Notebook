"""
Application Configuration
Pydantic settings with environment variable support
"""

import secrets
from typing import List, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""
    
    # ============================================
    # APP CONFIGURATION
    # ============================================
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=False)
    APP_NAME: str = Field(default="Structured Intelligence")
    
    # ============================================
    # DATABASE
    # ============================================
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://si_user:change_me@postgres:5432/structured_intelligence"
    )
    AUTO_RUN_MIGRATIONS: bool = Field(default=False)
    FORCE_RUN_MIGRATIONS_IN_PRODUCTION: bool = Field(default=False)
    
    # ============================================
    # VECTOR DATABASE (Qdrant)
    # ============================================
    QDRANT_URL: str = Field(default="http://qdrant:6333")
    QDRANT_API_KEY: str = Field(default="")
    QDRANT_COLLECTION: str = Field(default="si_documents")
    QDRANT_TIMEOUT_SECONDS: float = Field(default=5.0)
    EMBEDDING_DIM: int = Field(default=384)
    
    # ============================================
    # EMBEDDINGS (TEI)
    # ============================================
    EMBEDDING_URL: str = Field(default="http://tei:80")
    # A small model (about 130 MB of weights) so the default needs little memory. TEI serves this one model.
    EMBEDDING_MODEL: str = Field(default="BAAI/bge-small-en-v1.5")
    # The first call after a cold start can be slow while the model loads.
    EMBEDDING_TIMEOUT_SECONDS: float = Field(default=15.0)
    VECTOR_INDEXING_ENABLED: bool = Field(default=True)
    # Which service embeds documents until an admin chooses one in Settings: the bundled TEI container (default),
    # a local Ollama, or Ollama Cloud (its key is saved in Settings, never in the environment).
    EMBEDDING_PROVIDER: Literal["tei", "ollama", "ollama_cloud"] = Field(default="tei")
    # The model used when EMBEDDING_PROVIDER is ollama or ollama_cloud. TEI serves the one model in EMBEDDING_MODEL.
    OLLAMA_EMBED_MODEL: str = Field(default="embeddinggemma")

    # Where document memory lives. Only "builtin" (Postgres + Qdrant + TEI) exists today;
    # "smc" and "http" are reserved names and fail at startup until their adapters are written.
    MEMORY_BACKEND: Literal["builtin", "smc", "http"] = Field(default="builtin")
    
    # ============================================
    # REDIS
    # ============================================
    REDIS_URL: str = Field(default="redis://:change_me_too@redis:6379/0")
    REDIS_PASSWORD: str = Field(default="change_me_too")
    
    # ============================================
    # LLM CONFIGURATION
    # ============================================
    
    # Ollama (Primary)
    OLLAMA_URL: str = Field(default="http://host.docker.internal:11434")
    DEFAULT_MODEL: str = Field(default="llama3.2:3b-instruct-q4_K_M")
    # A cold model load can take far longer than a normal request, so reads get a generous limit.
    OLLAMA_CONNECT_TIMEOUT_SECONDS: float = Field(default=5.0)
    OLLAMA_READ_TIMEOUT_SECONDS: float = Field(default=120.0)

    # Claude API (Optional). Model IDs use hyphens and no date suffix, e.g. claude-sonnet-5-5.
    CLAUDE_API_KEY: str = Field(default="")
    CLAUDE_SONNET_MODEL: str = Field(default="claude-sonnet-5-5")
    CLAUDE_OPUS_MODEL: str = Field(default="claude-opus-5-5")
    CLAUDE_HAIKU_MODEL: str = Field(default="claude-haiku-5-5")
    CLAUDE_DEFAULT_MODEL: str = Field(default="claude-sonnet-5-5")
    CLAUDE_EFFORT: str = Field(default="medium")
    CLAUDE_MAX_OUTPUT_TOKENS: int = Field(default=16000)
    ANTHROPIC_REQUEST_TIMEOUT_SECONDS: float = Field(default=600.0)

    # OpenAI (Optional). Users normally save their own key in Settings; this is the server-wide fallback.
    OPENAI_API_KEY: str = Field(default="")
    # Used when the live model list cannot be read. The live list from the user's own key is what they pick from.
    OPENAI_DEFAULT_MODEL: str = Field(default="gpt-5.5")
    OPENAI_MAX_OUTPUT_TOKENS: int = Field(default=16000)
    OPENAI_REQUEST_TIMEOUT_SECONDS: float = Field(default=600.0)
    # Empty means "send nothing": which effort levels a model accepts differs by model.
    OPENAI_REASONING_EFFORT: str = Field(default="")

    @field_validator("OPENAI_REASONING_EFFORT")
    @classmethod
    def validate_openai_reasoning_effort(cls, v: str) -> str:
        allowed = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
        value = v.strip().lower()
        if value and value not in allowed:
            raise ValueError(f"OPENAI_REASONING_EFFORT must be empty or one of {sorted(allowed)}")
        return value

    # Chat history sent with each turn, and how long the live model list is cached.
    LLM_HISTORY_MESSAGES: int = Field(default=12)
    LLM_HISTORY_MAX_CHARS: int = Field(default=24000)
    LLM_MODEL_LIST_TTL_SECONDS: int = Field(default=300)

    @field_validator("CLAUDE_EFFORT")
    @classmethod
    def validate_claude_effort(cls, v: str) -> str:
        allowed = {"low", "medium", "high", "xhigh", "max"}
        value = v.strip().lower()
        if value not in allowed:
            raise ValueError(f"CLAUDE_EFFORT must be one of {sorted(allowed)}")
        return value

    # ============================================
    # STORED PROVIDER KEYS
    # ============================================
    # Comma-separated Fernet keys, newest first (older keys stay so existing rows still decrypt).
    # Lives only in the local environment, never in git. Not validated here on purpose: pydantic
    # would print a bad value in its error text. SecretBox validates it without echoing it.
    SECRETS_ENCRYPTION_KEY: SecretStr = Field(default=SecretStr(""))
    # When a user has not saved their own key, fall back to the server-wide key (CLAUDE_API_KEY).
    ALLOW_SERVER_PROVIDER_KEYS: bool = Field(default=True)

    # ============================================
    # AUTHENTICATION
    # ============================================
    JWT_SECRET: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=14)
    
    # Initial admin user
    ADMIN_EMAIL: str = Field(default="admin@structuredintelligence.com")
    ADMIN_PASSWORD: str = Field(default="change_me_immediately")
    ADMIN_NAME: str = Field(default="System Administrator")
    
    # ============================================
    # SMC (Structured Memory Core) INTEGRATION
    # ============================================
    SMC_ENABLED: bool = Field(default=True)
    SMC_ADMIN_TOKEN: str = Field(default="")
    SMC_AUDIT_ENABLED: bool = Field(default=True)
    
    # SMC Security Layers
    SMC_PI_GUARD_ENABLED: bool = Field(default=True)
    SMC_SANITIZER_ENABLED: bool = Field(default=True)
    SMC_RESOLVER_ENABLED: bool = Field(default=True)
    SMC_TOOL_WHITELIST_ENABLED: bool = Field(default=True)
    SMC_CIFS_AUDIT_ENABLED: bool = Field(default=True)
    
    # ============================================
    # CORS
    # ============================================
    CORS_ORIGINS: str | List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"]
    )
    
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    # ============================================
    # DOCUMENT PROCESSING
    # ============================================
    MAX_UPLOAD_SIZE_MB: int = Field(default=100)
    ALLOWED_EXTENSIONS: str | List[str] = Field(
        default=[".md", ".pdf", ".docx", ".txt", ".html"]
    )
    CHUNK_SIZE: int = Field(default=1000)
    CHUNK_OVERLAP: int = Field(default=200)
    UPLOAD_DIR: str = Field(default="/app/uploads")
    
    @field_validator("ALLOWED_EXTENSIONS", mode="before")
    @classmethod
    def parse_extensions(cls, v):
        if isinstance(v, str):
            return [ext.strip() for ext in v.split(",")]
        return v
    
    # ============================================
    # RATE LIMITING
    # ============================================
    RATE_LIMIT_PER_MINUTE: int = Field(default=60)
    RATE_LIMIT_BURST: int = Field(default=10)
    
    # ============================================
    # LOGGING
    # ============================================
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FILE: str = Field(default="/app/logs/si.log")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


# Create settings instance
settings = Settings()
