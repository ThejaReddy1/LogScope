from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DORIS_HOST: str = "doris-fe"
    DORIS_PORT: int = 9030
    DORIS_USER: str = "root"
    DORIS_PASSWORD: str = ""
    DORIS_DB: str = "otel"

    class Config:
        env_file = ".env"


settings = Settings()
