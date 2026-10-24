from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://sentra:sentra@localhost:5432/sentra"
    mistral_api_key: str = ""
    sentra_gh_token: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
