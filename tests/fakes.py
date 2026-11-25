"""In-memory реализации портов для юнит-тестов сервисов."""
from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from app.domain.entities import Profile, RefreshToken, SketchSummary, User
from app.domain.errors import EmailTaken


class FakeHasher:
    def hash(self, password: str) -> str:
        return "hashed:" + password

    def verify(self, password: str, hashed: str) -> bool:
        return hashed == "hashed:" + password


class FakeUserRepo:
    def __init__(self):
        self.items: dict[UUID, User] = {}

    def get_by_email(self, email):
        return next((u for u in self.items.values() if u.email == email), None)

    def get_by_id(self, user_id):
        return self.items.get(user_id)

    def add(self, user):
        if self.get_by_email(user.email):
            raise EmailTaken()
        self.items[user.id] = user
        return user


class FakeProfileRepo:
    def __init__(self):
        self.items: dict[UUID, Profile] = {}

    def get(self, user_id):
        return self.items.get(user_id)

    def upsert(self, user_id, patch):
        current = self.items.get(user_id) or Profile(user_id=user_id)
        self.items[user_id] = replace(current, **patch)
        return self.items[user_id]


class FakeTokenRepo:
    def __init__(self):
        self.items: dict[UUID, RefreshToken] = {}

    def add(self, token):
        self.items[token.id] = token

    def get_by_hash(self, token_hash):
        return next((t for t in self.items.values() if t.token_hash == token_hash), None)

    def revoke(self, token_id):
        token = self.items[token_id]
        if token.revoked:
            return False
        token.revoked = True
        return True


class FakeSketchRepo:
    def __init__(self, items: list[SketchSummary] | None = None):
        self.items = items or []

    def list_by_user(self, user_id, page, limit):
        start = (page - 1) * limit
        return self.items[start:start + limit], len(self.items)
