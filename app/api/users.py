from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from ..domain.entities import Profile, User
from ..services.users import UserService
from .deps import current_user_id, get_user_service
from .schemas import MeResponse, ProfileOut, ProfileUpdate, SketchItem, SketchPage, SketchS3

router = APIRouter(prefix="/users/me", tags=["users"])


def _me(user: User, profile: Profile | None) -> MeResponse:
    return MeResponse(
        id=user.id, email=user.email, role=user.role, is_active=user.is_active, created_at=user.created_at,
        profile=ProfileOut(display_name=profile.display_name, avatar_s3_key=profile.avatar_s3_key,
                           bio=profile.bio, preferences=profile.preferences) if profile else None,
    )


@router.get("", response_model=MeResponse)
def get_me(user_id: UUID = Depends(current_user_id), svc: UserService = Depends(get_user_service)):
    return _me(*svc.get_me(user_id))


@router.put("/profile", response_model=MeResponse)
def update_profile(body: ProfileUpdate, user_id: UUID = Depends(current_user_id),
                   svc: UserService = Depends(get_user_service)):
    return _me(*svc.update_profile(user_id, body.model_dump(exclude_unset=True)))


@router.get("/sketches", response_model=SketchPage)
def my_sketches(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
                user_id: UUID = Depends(current_user_id), svc: UserService = Depends(get_user_service)):
    items, total = svc.list_sketches(user_id, page, limit)
    return SketchPage(
        items=[SketchItem(id=s.id, title=s.title, source=s.source, s3=SketchS3(thumbnail=s.thumbnail),
                          created_at=s.created_at) for s in items],
        total=total, page=page, limit=limit,
    )
