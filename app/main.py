import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.messaging_api import router as messaging_router
from app.config import get_settings
from app.services.reminders import reminder_scan_loop
from app.services.redis_store import redis_ping
from app.database import SessionLocal
from app.services.calendar import reconcile_calendar
from app.services.email_receiver import email_poll_loop

BASE_DIR = Path(__file__).resolve().parent

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    with SessionLocal() as db:
        reconcile_calendar(db)
    scanner = asyncio.create_task(
        reminder_scan_loop(settings.reminder_scan_interval_seconds)
    )
    email_poller = (
        asyncio.create_task(email_poll_loop(settings))
        if settings.email_imap_enabled
        else None
    )
    yield
    scanner.cancel()
    if email_poller:
        email_poller.cancel()
    try:
        await scanner
    except asyncio.CancelledError:
        pass
    if email_poller:
        try:
            await email_poller
        except asyncio.CancelledError:
            pass


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)
app.include_router(router)
app.include_router(messaging_router)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "redis": "ok" if redis_ping() else "degraded",
        "email_imap": (
            "enabled" if get_settings().email_imap_enabled else "disabled"
        ),
    }
