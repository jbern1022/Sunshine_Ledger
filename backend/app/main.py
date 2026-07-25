from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import bills, flags, map as map_router

app = FastAPI(
    title="Sunshine Ledger API",
    description="Florida state and local bill tracker — plain-language summaries, geographic impact, sourced claims.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # MVP: public read-only API, no auth/credentials involved.
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(bills.router)
app.include_router(map_router.router)
app.include_router(flags.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
