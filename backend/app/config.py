from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central app configuration, sourced from environment / .env.

    Per the BRD's state-agnostic requirement, jurisdiction values (state,
    cities) are configuration here rather than hardcoded in pipeline code.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://sunshine:sunshine_dev_only@localhost:5432/sunshine_ledger"

    legiscan_api_key: str = ""
    legiscan_state: str = "FL"

    legistar_clients: str = "miami,jacksonville"

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    @property
    def legistar_client_list(self) -> list[str]:
        return [c.strip() for c in self.legistar_clients.split(",") if c.strip()]


settings = Settings()
