from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    database_url: str

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Google OAuth
    google_client_id: str

    # LinkedIn OAuth (optional — required only when LinkedIn login is used)
    linkedin_client_id: str | None = None
    linkedin_client_secret: str | None = None
    linkedin_redirect_uri: str | None = None

    # LLM provider — selects which chat backend get_chat_provider() returns.
    # Supported: azure_openai
    # Add new values as implementations are added to app/services/llm/
    llm_provider: str = "azure_openai"

    # Azure OpenAI
    azure_openai_api_key: str
    azure_openai_endpoint: str
    azure_openai_chat_deployment: str = "gpt-4o-mini"
    azure_openai_embedding_deployment: str = "text-embedding-3-large"
    azure_openai_api_version: str = "2025-01-01-preview"
    azure_openai_embedding_api_version: str = "2023-05-15"

    # Storage — local for dev, swap to azure blob for prod
    storage_backend: str = "local"  # "local" | "azure"
    local_storage_path: str = "./uploads"
    azure_blob_connection_string: str = ""
    azure_blob_container: str = "studybuddy-documents"

    # CORS — comma-separated list of allowed origins
    # e.g. CORS_ORIGINS=http://localhost:3000,https://app.studybuddy.com
    cors_origins: str = "http://localhost:3000"

    # App
    environment: str = "development"
    max_file_size_mb: int = 50


settings = Settings()
