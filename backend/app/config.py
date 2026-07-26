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

    legistar_clients: str = "miamifl,jaxcityc"

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Comma-separated list of origins allowed to call this API from a
    # browser. Defaults to local dev only -- production deployments must
    # set this explicitly (e.g. https://sunshineledger.josephbernal.com)
    # rather than relying on a wildcard.
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:3010"

    @property
    def legistar_client_list(self) -> list[str]:
        return [c.strip() for c in self.legistar_clients.split(",") if c.strip()]

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


settings = Settings()
