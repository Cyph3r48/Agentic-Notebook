"""
Application Configuration
Pydantic settings with environment variable support
"""

import secrets
from typing import List

from pydantic import Field, field_validator
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
    EMBEDDING_DIM: int = Field(default=1024)
    
    # ============================================
    # EMBEDDINGS (TEI)
    # ============================================
    EMBEDDING_URL: str = Field(default="http://tei:80")
    EMBEDDING_MODEL: str = Field(default="BAAI/bge-large-en-v1.5")
    VECTOR_INDEXING_ENABLED: bool = Field(default=False)
    
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
