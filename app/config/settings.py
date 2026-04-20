from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")

    # Azure Blob Storage
    azure_blob_connection_string: str = Field(default="")
    azure_blob_container: str = Field(default="contracts")

    # Azure Document Intelligence
    document_intelligence_endpoint: str = Field(default="")
    document_intelligence_key: str = Field(default="")

    # Observability
    appinsights_connection_string: str = Field(default="")
    langfuse_public_key: str = Field(default="")
    langfuse_secret_key: str = Field(default="")
    langfuse_host: str = Field(default="https://cloud.langfuse.com")


settings = Settings()
