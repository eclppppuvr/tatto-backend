"""Интеграционные тесты API на SQLite in-memory. Нужны: fastapi, httpx, sqlalchemy, bcrypt, email-validator."""
import unittest

try:
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    import bcrypt  # noqa: F401
    HAVE_DEPS = True
except ImportError:
    HAVE_DEPS = False

if HAVE_DEPS:
    from app.config import Settings
    from app.db.models import Base
    from app.main import create_app

PASSWORD = "securePass123"


@unittest.skipUnless(HAVE_DEPS, "не установлены зависимости из requirements-dev.txt")
class ApiTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        settings = Settings(db_url="sqlite://", jwt_secret="s" * 32, bcrypt_rounds=4)
        self.client = TestClient(create_app(settings, engine))

    def register(self, email="user@example.com"):
        r = self.client.post("/v1/auth/register", json={"email": email, "password": PASSWORD})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    @staticmethod
    def auth(tokens):
        return {"Authorization": f"Bearer {tokens['access_token']}"}

    def test_register_contract(self):
        body = self.register()
        self.assertEqual(body["role"], "client")
        self.assertEqual(set(body), {"id", "email", "role", "access_token", "refresh_token"})

    def test_register_duplicate_409(self):
        self.register()
        r = self.client.post("/v1/auth/register", json={"email": "USER@example.com", "password": PASSWORD})
        self.assertEqual(r.status_code, 409)

    def test_register_validation_422(self):
        self.assertEqual(self.client.post("/v1/auth/register", json={"email": "nope", "password": PASSWORD}).status_code, 422)
        self.assertEqual(self.client.post("/v1/auth/register", json={"email": "a@b.co", "password": "short"}).status_code, 422)

    def test_login_ok_and_401(self):
        self.register()
        ok = self.client.post("/v1/auth/login", json={"email": "user@example.com", "password": PASSWORD})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["user"]["email"], "user@example.com")
        bad = self.client.post("/v1/auth/login", json={"email": "user@example.com", "password": "wrongwrong"})
        self.assertEqual(bad.status_code, 401)

    def test_bruteforce_lock(self):
        self.register()
        for _ in range(5):
            self.client.post("/v1/auth/login", json={"email": "user@example.com", "password": "wrongwrong"})
        r = self.client.post("/v1/auth/login", json={"email": "user@example.com", "password": PASSWORD})
        self.assertEqual(r.status_code, 429)

    def test_refresh_rotation(self):
        tokens = self.register()
        r = self.client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        self.assertEqual(r.status_code, 200)
        again = self.client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        self.assertEqual(again.status_code, 401)

    def test_me_requires_token(self):
        self.assertEqual(self.client.get("/v1/users/me").status_code, 401)
        self.assertEqual(self.client.get("/v1/users/me", headers={"Authorization": "Bearer junk"}).status_code, 401)

    def test_me_and_profile_update(self):
        tokens = self.register()
        me = self.client.get("/v1/users/me", headers=self.auth(tokens)).json()
        self.assertIsNone(me["profile"])
        r = self.client.put("/v1/users/me/profile", headers=self.auth(tokens),
                            json={"display_name": "Иван Петров", "bio": "Тату-мастер", "preferences": {"theme": "dark"}})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["profile"]["display_name"], "Иван Петров")
        again = self.client.get("/v1/users/me", headers=self.auth(tokens)).json()
        self.assertEqual(again["profile"]["preferences"], {"theme": "dark"})

    def test_profile_validation(self):
        tokens = self.register()
        r = self.client.put("/v1/users/me/profile", headers=self.auth(tokens), json={"display_name": "x" * 101})
        self.assertEqual(r.status_code, 422)

    def test_sketches_empty_and_validation(self):
        tokens = self.register()
        r = self.client.get("/v1/users/me/sketches", headers=self.auth(tokens))
        self.assertEqual(r.json(), {"items": [], "total": 0, "page": 1, "limit": 20})
        for q in ("page=0", "limit=101"):
            self.assertEqual(self.client.get(f"/v1/users/me/sketches?{q}", headers=self.auth(tokens)).status_code, 422)

    def test_logout_revokes_refresh(self):
        tokens = self.register()
        r = self.client.post("/v1/auth/logout", headers=self.auth(tokens), json={"refresh_token": tokens["refresh_token"]})
        self.assertEqual(r.json(), {"message": "Logged out"})
        self.assertEqual(self.client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code, 401)

    def test_logout_without_body(self):
        tokens = self.register()
        self.assertEqual(self.client.post("/v1/auth/logout", headers=self.auth(tokens)).status_code, 200)


if __name__ == "__main__":
    unittest.main()
