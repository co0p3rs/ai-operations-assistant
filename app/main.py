import json
import logging
import uuid

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, status

from app.access import is_allowed
from app.config import get_settings
from app.dedupe import EventDeduplicator
from app.providers import DemoAnalyticsProvider, ProviderRegistry
from app.security import verify_signature

logger = logging.getLogger(__name__)
settings = get_settings()
deduplicator = EventDeduplicator(settings.event_ttl_seconds)
registry = ProviderRegistry([DemoAnalyticsProvider()])

app = FastAPI(title="AI Operations Assistant", docs_url="/docs" if settings.environment != "production" else None)


async def process_event(event: dict[str, object], request_id: str) -> None:
    role = str(event.get("role", "viewer"))
    provider = str(event.get("provider", "analytics"))
    if not is_allowed(role, provider):
        logger.warning("request_denied request_id=%s provider=%s", request_id, provider)
        return
    try:
        result = await registry.execute(provider, str(event.get("text", "")))
        logger.info("request_complete request_id=%s result_keys=%s", request_id, sorted(result))
    except KeyError:
        logger.warning("unknown_provider request_id=%s provider=%s", request_id, provider)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhooks/events", status_code=status.HTTP_202_ACCEPTED)
async def webhook(request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
    body = await request.body()
    timestamp = request.headers.get("x-event-timestamp", "")
    signature = request.headers.get("x-event-signature", "")
    if not verify_signature(settings.webhook_signing_secret, timestamp, body, signature):
        raise HTTPException(status_code=401, detail="invalid signature")

    try:
        event = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid JSON") from exc

    event_id = str(event.get("event_id", ""))
    if not event_id:
        raise HTTPException(status_code=422, detail="event_id is required")
    if not deduplicator.accept(event_id):
        return {"status": "duplicate", "request_id": "existing"}

    request_id = str(uuid.uuid4())
    background_tasks.add_task(process_event, event, request_id)
    return {"status": "accepted", "request_id": request_id}
