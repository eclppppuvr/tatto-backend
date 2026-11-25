import unittest
from datetime import datetime, timezone
from uuid import uuid4

from app.domain.entities import Role, SketchSummary, User
from app.domain.errors import AccountBlocked, UserNotFound
from app.services.users import UserService
from tests.fakes import FakeProfileRepo, FakeSketchRepo, FakeUserRepo

NOW = datetime(2026, 11, 24, tzinfo=timezone.utc)


def make_user(active=True):
    return User(uuid4(), "a@b.co", "h", Role.CLIENT, active, NOW, NOW)


class UserServiceTests(unittest.TestCase):
    def setUp(self):
        self.users, self.profiles = FakeUserRepo(), FakeProfileRepo()
        self.sketches = FakeSketchRepo([
            SketchSummary(f"sk_{i}", f"t{i}", "extract", f"sketches/{i}_thumb.jpg", NOW) for i in range(45)
        ])
        self.svc = UserService(self.users, self.profiles, self.sketches)
        self.user = self.users.add(make_user())

    def test_me_without_profile_is_none(self):
        user, profile = self.svc.get_me(self.user.id)
        self.assertEqual(user.id, self.user.id)
        self.assertIsNone(profile)

    def test_me_unknown_user(self):
        with self.assertRaises(UserNotFound):
            self.svc.get_me(uuid4())

    def test_me_blocked_user(self):
        blocked = self.users.add(User(uuid4(), "c@b.co", "h", Role.CLIENT, False, NOW, NOW))
        with self.assertRaises(AccountBlocked):
            self.svc.get_me(blocked.id)

    def test_update_profile_partial(self):
        self.svc.update_profile(self.user.id, {"display_name": "Иван", "bio": "мастер"})
        _, p = self.svc.update_profile(self.user.id, {"preferences": {"theme": "dark"}})
        self.assertEqual((p.display_name, p.bio, p.preferences), ("Иван", "мастер", {"theme": "dark"}))

    def test_update_profile_ignores_foreign_fields(self):
        _, p = self.svc.update_profile(self.user.id, {"display_name": "X", "avatar_s3_key": "hack", "role": "admin"})
        self.assertEqual(p.display_name, "X")
        self.assertIsNone(p.avatar_s3_key)

    def test_update_profile_null_preferences_become_empty(self):
        _, p = self.svc.update_profile(self.user.id, {"preferences": None})
        self.assertEqual(p.preferences, {})

    def test_sketch_pagination(self):
        items, total = self.svc.list_sketches(self.user.id, page=3, limit=20)
        self.assertEqual((len(items), total), (5, 45))


if __name__ == "__main__":
    unittest.main()
