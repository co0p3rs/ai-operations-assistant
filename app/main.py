import logging

from fastapi import FastAPI

from app.admin import router as admin_router
from app.bi_api import router as bi_router
from app.config import get_settings
from app.health import router as health_router
from app.webhook import router as webhook_router

logging.basicConfig(level=logging.INFO)
settings = get_settings()

app = FastAPI(
    title="AI Operations Assistant",
    description=(
        "Signed chat webhooks, deny-by-default RBAC, pluggable read-only "
        "providers, and a dual-model answering path. Uses fictional "
        "Northstar Outfitters data."
    ),
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

app.include_router(health_router)
app.include_router(webhook_router)
app.include_router(admin_router)
app.include_router(bi_router)
