from pydantic import model_validator
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

    # LegiScan's free tier: 10,000 calls a month from 2026-10-01. The
    # nightly cap (x 31 nights = 7,750 at 250) leaves room for manual runs;
    # raise it in the busiest weeks of session, lower it in summer. The
    # monthly limit drives the 70%/90% ntfy alerts. Documents come from
    # flsenate.gov (10 s apart), capped per night so a busy night can't run
    # for hours.
    legiscan_nightly_call_budget: int = 250
    legiscan_monthly_limit: int = 10000
    flsenate_nightly_documents: int = 300

    # ntfy topic URL for operational alerts (e.g. the LegiScan usage
    # warnings), the same topic Kuma notifies. Empty: alerts are only logged.
    ntfy_alert_url: str = ""

    # Free signup: https://api.census.gov/data/key_signup.html. Required as
    # of 2026-09 -- unauthenticated requests now redirect to a key-missing
    # error page rather than serving data.
    census_api_key: str = ""

    # Optional. BLS's public API works keyless (verified 2026-09-15) at a
    # lower daily quota (25 req/day/IP vs. 500 with a registered key). Free
    # signup: https://data.bls.gov/registrationEngine/
    bls_api_key: str = ""

    legistar_clients: str = "miamifl,jaxcityc"

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # Optional cheaper model for the summary fields that measured as
    # quality-insensitive (BRD 6's cost-aware requirement). Empty means
    # every prompt uses `ollama_model` -- see docs/LLM_MODEL_ROUTING.md for
    # the measurements behind the default and when turning this on is
    # actually worth it.
    ollama_model_fast: str = ""

    # Bill layers (Bill Says / Interpretation / Expected Effect) can run a
    # different, larger model than summaries -- see the 2026-09-24 bill
    # layers quality plan. Empty means "use ollama_model" (the historical
    # behavior for deployments that never set this), resolved below rather
    # than defaulted statically so it still tracks an overridden
    # ollama_model.
    ollama_layers_model: str = ""

    @model_validator(mode="after")
    def _default_layers_model(self) -> "Settings":
        if not self.ollama_layers_model:
            self.ollama_layers_model = self.ollama_model
        return self

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Comma-separated list of origins allowed to call this API from a
    # browser. Defaults to local dev only -- production deployments must
    # set this explicitly (e.g. https://sunshineledger.josephbernal.com)
    # rather than relying on a wildcard.
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:3010"

    # HTTP Basic Auth for admin-only endpoints (currently: flag review).
    # Empty password means those endpoints reject everything -- see
    # app/auth.py's fail-closed behavior.
    admin_username: str = "admin"
    admin_password: str = ""

    @property
    def legistar_client_list(self) -> list[str]:
        return [c.strip() for c in self.legistar_clients.split(",") if c.strip()]

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


settings = Settings()
