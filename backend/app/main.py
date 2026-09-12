from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    accounts,
    admin,
    advice,
    assets,
    auth,
    backup,
    budgets,
    cash_flow,
    categories,
    crypto,
    dashboard,
    goals,
    insights,
    net_worth,
    recurring,
    reports,
    settings as settings_routes,
    tags,
    transactions,
)
from app.core.config import APP_VERSION, get_settings

settings = get_settings()


def _check_jwt_secret_is_configured() -> None:
    """Fail fast if AURUM_JWT_SECRET was left at its placeholder default.

    This is categorically different from the frontend's "Basic Auth unset is
    fine for localhost" tolerance (see docker-compose.yml): an unset Basic
    Auth password means *no* auth, but a JWT secret left at the placeholder
    means auth *exists but is worthless* — the signing key is public in this
    open-source repository, so every access/refresh token the app would ever
    issue is forgeable by anyone who has read the source. Refusing to start
    (rather than just logging a warning) is the only way to guarantee this
    never quietly ships to a real deployment.
    """
    if get_settings().jwt_secret == "change-me-in-production":
        raise RuntimeError(
            "AURUM_JWT_SECRET is still the placeholder default — set it to a "
            "real random value (e.g. `openssl rand -hex 32`) before starting. "
            "Every login token is forgeable until you do."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _check_jwt_secret_is_configured()
    yield


app = FastAPI(
    title="Moneta API",
    version=APP_VERSION,
    lifespan=lifespan,
    # Docs live under /api/* because nginx only proxies that prefix to the
    # backend (see frontend/nginx.conf) — everything else falls through to
    # the SPA's index.html, which is why the defaults (/docs, /openapi.json)
    # would silently 404 through the reverse proxy.
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS stays off unless someone deliberately opens it, and credentials are
# only granted to a pinned list. Starlette answers a credentialed "*" by
# echoing back whatever Origin asked instead of a literal "*" — so the two
# together turn any page the user happens to have open into an authenticated
# client of their instance, which is exactly what the README's "fine if it's
# only reachable from localhost" advice assumes can't happen.
cors_origins = settings.cors_origins_list
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials="*" not in cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(accounts.router, prefix="/api")
app.include_router(categories.router, prefix="/api")
app.include_router(transactions.router, prefix="/api")
app.include_router(assets.router, prefix="/api")
app.include_router(net_worth.router, prefix="/api")
app.include_router(backup.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(insights.router, prefix="/api")
app.include_router(settings_routes.router, prefix="/api")
app.include_router(budgets.router, prefix="/api")
app.include_router(advice.router, prefix="/api")
app.include_router(goals.router, prefix="/api")
app.include_router(recurring.router, prefix="/api")
app.include_router(cash_flow.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
app.include_router(crypto.router, prefix="/api")


@app.get("/api/health")
async def health() -> dict[str, str]:
    # version rides along so the frontend's Settings page can show which
    # release is actually running without a separate authenticated endpoint —
    # this route is already auth_basic-exempt for Docker's HEALTHCHECK.
    return {"status": "ok", "version": APP_VERSION}
