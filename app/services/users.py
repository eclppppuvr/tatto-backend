"""INT-4, INT-5, INT-6: профиль и история эскизов."""
from __future__ import annotations

from uuid import UUID

from ..domain.entities import Profile, SketchSummary, User
from ..domain.errors import AccountBlocked, UserNotFound
from ..domain.ports import ProfileRepo, SketchRepo, UserRepo

PROFILE_FIELDS = ("display_name", "bio", "preferences")


class UserService:
    def __init__(self, users: UserRepo, profiles: ProfileRepo, sketches: SketchRepo):
        self._users = users
        self._profiles = profiles
        self._sketches = sketches

    def _active_user(self, user_id: UUID) -> User:
        user = self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFound()
        if not user.is_active:
            raise AccountBlocked()
        return user

    def get_me(self, user_id: UUID) -> tuple[User, Profile | None]:
        user = self._active_user(user_id)
        return user, self._profiles.get(user_id)

    def update_profile(self, user_id: UUID, patch: dict) -> tuple[User, Profile]:
        user = self._active_user(user_id)
        clean = {k: v for k, v in patch.items() if k in PROFILE_FIELDS}
        if "preferences" in clean and clean["preferences"] is None:
            clean["preferences"] = {}
        return user, self._profiles.upsert(user_id, clean)

    def list_sketches(self, user_id: UUID, page: int, limit: int) -> tuple[list[SketchSummary], int]:
        return self._sketches.list_by_user(user_id, page, limit)
