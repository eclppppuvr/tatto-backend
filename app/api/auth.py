from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from ..services.auth import AuthService
from .deps import client_ip, current_user_id, get_auth_service
from .schemas import (LoginRequest, LoginResponse, LogoutRequest, MessageResponse, RefreshRequest,
                      RegisterRequest, RegisterResponse, TokenPairResponse, UserShort)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201, response_model=RegisterResponse)
def register(body: RegisterRequest, svc: AuthService = Depends(get_auth_service)):
    user, tokens = svc.register(body.email, body.password)
    return RegisterResponse(id=user.id, email=user.email, role=user.role,
                            access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, ip: str = Depends(client_ip), svc: AuthService = Depends(get_auth_service)):
    user, tokens = svc.login(body.email, body.password, ip)
    return LoginResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token,
                         user=UserShort(id=user.id, email=user.email, role=user.role))


@router.post("/refresh", response_model=TokenPairResponse)
def refresh(body: RefreshRequest, svc: AuthService = Depends(get_auth_service)):
    tokens = svc.refresh(body.refresh_token)
    return TokenPairResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@router.post("/logout", response_model=MessageResponse)
def logout(body: LogoutRequest | None = None, user_id: UUID = Depends(current_user_id),
           svc: AuthService = Depends(get_auth_service)):
    svc.logout(user_id, body.refresh_token if body else None)
    return MessageResponse(message="Logged out")
