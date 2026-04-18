from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Azure OpenAI
    azure_openai_endpoint: str = Field(default="mock://openai")
    azure_openai_api_key: str = Field(default="mock-key")
    azure_openai_deployment: str = Field(default="gpt-4o")

    # Azure Blob Storage
    azure_blob_connection_string: str = Field(default="mock://blob")
    azure_blob_container: str = Field(default="contracts")

    # Azure Document Intelligence
    document_intelligence_endpoint: str = Field(default="mock://doc-intel")
    document_intelligence_key: str = Field(default="mock-key")

    # Observability
    appinsights_connection_string: str = Field(default="")
    langfuse_public_key: str = Field(default="")
    langfuse_secret_key: str = Field(default="")
    langfuse_host: str = Field(default="https://cloud.langfuse.com")

    # Dev
    use_mocks: bool = Field(default=True)


settings = Settings()
