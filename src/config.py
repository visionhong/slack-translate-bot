from pydantic import Field
from pydantic_settings import BaseSettings


class SlackConfig(BaseSettings):
    bot_token: str = Field(..., alias="SLACK_BOT_TOKEN")
    signing_secret: str = Field(..., alias="SLACK_SIGNING_SECRET")


class AzureOpenAIConfig(BaseSettings):
    api_key: str = Field(..., alias="AZURE_OPENAI_API_KEY")
    endpoint: str = Field(..., alias="AZURE_OPENAI_ENDPOINT")
    api_version: str = Field("2024-02-15-preview", alias="AZURE_OPENAI_API_VERSION")
    deployment_name: str = Field("gpt-35-turbo", alias="AZURE_OPENAI_DEPLOYMENT")


class CacheConfig(BaseSettings):
    ttl: int = Field(3600, alias="CACHE_TTL")


class AppConfig(BaseSettings):
    environment: str = Field("development", alias="ENVIRONMENT")
    log_level: str = Field("INFO", alias="LOG_LEVEL")


settings = type("Settings", (), {
    "slack": SlackConfig(),
    "azure_openai": AzureOpenAIConfig(),
    "cache": CacheConfig(),
    "app": AppConfig(),
})()