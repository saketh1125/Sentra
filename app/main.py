from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.routers import ask as ask_router
from app.routers import docs as docs_router
from app.routers import pr as pr_router
from app.routers import repos as repos_router
from app.routers import scan as scan_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from alembic.config import Config
    from alembic import command as alembic_command
    import pathlib
    import asyncio

    cfg = Config(str(pathlib.Path(__file__).resolve().parents[1] / "alembic.ini"))
    migration_url = settings.database_url.replace("+asyncpg", "+psycopg")
    cfg.set_main_option("sqlalchemy.url", migration_url.replace("%", "%%"))
    await asyncio.to_thread(alembic_command.upgrade, cfg, "head")
    yield


app = FastAPI(title="Sentra API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(repos_router.router)
app.include_router(ask_router.router)
app.include_router(scan_router.router)
app.include_router(docs_router.router)
app.include_router(pr_router.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready", "db": "ok"}
    except Exception as e:
        return {"status": "degraded", "db": str(e)}
