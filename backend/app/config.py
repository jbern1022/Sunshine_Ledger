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

    # Free key: https://api.congress.gov/sign-up/ . Limit 5,000 requests/hour.
    congress_api_key: str = ""

    # Where promise snapshots (raw fetched pages) are stored, by content hash.
    snapshot_dir: str = "/data/snapshots"
    # Politeness for crawling candidates' own sites: seconds between requests
    # to one host (the approved iQM2 default is 60), and a cap per run.
    crawl_pace_seconds: float = 60.0
    crawl_max_requests: int = 400
    # iQM2 portals publish `Crawl-delay: 60`; that is also our default and a
    # floor. A run stops at whichever cap it hits first and resumes next time.
    iqm2_pace_seconds: float = 60.0
    iqm2_max_requests_per_run: int = 150
    iqm2_max_minutes_per_run: int = 150
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
    # The nightly generates the Who it affects block only once this is on:
    # off until a quality report (review_bill_layers --who-only) is signed
    # off, as with every earlier layer.
    layers_who_it_affects: bool = False

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

    # Reader accounts (docs/ADR_READER_AUTH_COGNITO.md). Off: every /auth and /watchlist route answers 404.
    # Public registration additionally stays closed until the privacy, deletion, security and legal gates pass.
    auth_enabled: bool = False
    cognito_region: str = ""
    cognito_user_pool_id: str = ""
    cognito_client_id: str = ""
    cognito_client_secret: str = ""
    # Host-only cookie unless a parent domain is set (the site and API are separate subdomains today).
    session_cookie_domain: str = ""
    session_cookie_secure: bool = True

    @property
    def legistar_client_list(self) -> list[str]:
        return [c.strip() for c in self.legistar_clients.split(",") if c.strip()]

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


settings = Settings()
