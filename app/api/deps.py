from __future__ import annotations

from typing import Iterator
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..domain.errors import InvalidAccessToken
from ..security import decode_access_token
from ..services.auth import AuthService
from ..services.sketches import EmptySketchRepo
from ..services.users import UserService
from ..db.repos import SqlJobRepo, SqlProfileRepo, SqlRefreshTokenRepo, SqlUserRepo
from ..services.jobs import JobService

_bearer = HTTPBearer(auto_error=False)


def get_session(request: Request) -> Iterator[Session]:
    """Одна транзакция на запрос: commit при успехе, rollback при любой ошибке."""
    session = request.app.state.session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_auth_service(request: Request, session: Session = Depends(get_session)) -> AuthService:
    state = request.app.state
    return AuthService(SqlUserRepo(session), SqlRefreshTokenRepo(session), state.hasher,
                       state.settings, state.limiter)


def get_user_service(session: Session = Depends(get_session)) -> UserService:
    # TB-03/TB-04: заменить EmptySketchRepo на реализацию поверх MongoDB.
    return UserService(SqlUserRepo(session), SqlProfileRepo(session), EmptySketchRepo())


def get_job_service(request: Request, session: Session = Depends(get_session)) -> JobService:
    return JobService(SqlJobRepo(session), request.app.state.dispatcher, commit=session.commit)


def current_user_id(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> UUID:
    if creds is None:
        raise InvalidAccessToken()
    return decode_access_token(creds.credentials, request.app.state.settings.jwt_secret).user_id


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
