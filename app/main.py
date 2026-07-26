import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.config import get_settings
from app.services.reminders import reminder_scan_loop
from app.services.redis_store import redis_ping
from app.database import SessionLocal
from app.services.calendar import reconcile_calendar

BASE_DIR = Path(__file__).resolve().parent

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    with SessionLocal() as db:
        reconcile_calendar(db)
    scanner = asyncio.create_task(
        reminder_scan_loop(settings.reminder_scan_interval_seconds)
    )
    yield
    scanner.cancel()
    try:
        await scanner
    except asyncio.CancelledError:
        pass


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)
app.include_router(router)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "redis": "ok" if redis_ping() else "degraded",
    }
