"""Точка входа. Запуск: uvicorn app.main:create_app --factory"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from .api import auth, users
from .config import Settings
from .db.session import make_engine, make_session_factory
from .domain.errors import AppError
from .rate_limit import LoginRateLimiter
from .security import BcryptHasher


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = engine or make_engine(settings.db_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(title="AI Tattoo Studio API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = make_session_factory(engine)
    app.state.hasher = BcryptHasher(settings.bcrypt_rounds)
    app.state.limiter = LoginRateLimiter(settings.login_max_failures, settings.login_block_minutes * 60)

    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                           allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)

    @app.exception_handler(OperationalError)
    async def _db_down(_: Request, exc: OperationalError):  # TB-02 §5.2
        return JSONResponse({"detail": "Сервис временно недоступен"}, status_code=503)

    app.include_router(auth.router, prefix="/v1")
    app.include_router(users.router, prefix="/v1")

    @app.get("/health", tags=["service"])
    def health():
        return {"status": "ok"}

    return app
