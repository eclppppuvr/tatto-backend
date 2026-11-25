import unittest
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.domain.errors import (AccountBlocked, EmailTaken, InvalidCredentials, InvalidRefreshToken,
                               RevokedRefreshToken, TooManyAttempts)
from app.rate_limit import LoginRateLimiter
from app.security import decode_access_token, hash_refresh_token
from app.services.auth import AuthService
from tests.fakes import FakeHasher, FakeTokenRepo, FakeUserRepo

SETTINGS = Settings(db_url="sqlite://", jwt_secret="s" * 32)


class AuthServiceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)  # PyJWT проверяет exp по реальным часам
        self.users, self.tokens = FakeUserRepo(), FakeTokenRepo()
        self.limiter = LoginRateLimiter(5, 900)
        self.svc = AuthService(self.users, self.tokens, FakeHasher(), SETTINGS, self.limiter,
                               clock=lambda: self.now)

    # INT-1
    def test_register_returns_client_with_tokens(self):
        user, pair = self.svc.register("User@Example.com", "securePass123")
        self.assertEqual(user.email, "user@example.com")
        self.assertEqual(user.role.value, "client")
        self.assertNotEqual(user.hashed_password, "securePass123")
        self.assertEqual(decode_access_token(pair.access_token, SETTINGS.jwt_secret).user_id, user.id)
        self.assertTrue(pair.refresh_token.startswith("rt_"))

    def test_register_stores_only_refresh_hash(self):
        _, pair = self.svc.register("a@b.co", "securePass123")
        stored = list(self.tokens.items.values())[0]
        self.assertEqual(stored.token_hash, hash_refresh_token(pair.refresh_token))
        self.assertNotEqual(stored.token_hash, pair.refresh_token)
        self.assertEqual(stored.expires_at, self.now + timedelta(days=7))

    def test_register_duplicate_email_case_insensitive(self):
        self.svc.register("a@b.co", "securePass123")
        with self.assertRaises(EmailTaken):
            self.svc.register("A@B.CO", "otherPass123")

    # INT-2
    def test_login_ok(self):
        self.svc.register("a@b.co", "securePass123")
        user, pair = self.svc.login("a@b.co", "securePass123", "1.1.1.1")
        self.assertEqual(user.email, "a@b.co")
        self.assertTrue(pair.access_token)

    def test_login_wrong_password_and_unknown_email_same_error(self):
        self.svc.register("a@b.co", "securePass123")
        with self.assertRaises(InvalidCredentials) as e1:
            self.svc.login("a@b.co", "wrongPass", "1.1.1.1")
        with self.assertRaises(InvalidCredentials) as e2:
            self.svc.login("nobody@b.co", "securePass123", "1.1.1.1")
        self.assertEqual(e1.exception.message, e2.exception.message)

    def test_login_blocked_account(self):
        user, _ = self.svc.register("a@b.co", "securePass123")
        user.is_active = False
        with self.assertRaises(AccountBlocked):
            self.svc.login("a@b.co", "securePass123", "1.1.1.1")

    def test_blocked_account_does_not_leak_on_wrong_password(self):
        user, _ = self.svc.register("a@b.co", "securePass123")
        user.is_active = False
        with self.assertRaises(InvalidCredentials):
            self.svc.login("a@b.co", "wrongPass", "1.1.1.1")

    def test_bruteforce_blocks_ip_even_with_right_password(self):
        self.svc.register("a@b.co", "securePass123")
        for _ in range(5):
            with self.assertRaises(InvalidCredentials):
                self.svc.login("a@b.co", "bad", "9.9.9.9")
        with self.assertRaises(TooManyAttempts):
            self.svc.login("a@b.co", "securePass123", "9.9.9.9")
        self.svc.login("a@b.co", "securePass123", "8.8.8.8")  # другой IP — ок

    # INT-3
    def test_refresh_rotates_and_revokes_old(self):
        _, pair = self.svc.register("a@b.co", "securePass123")
        new_pair = self.svc.refresh(pair.refresh_token)
        self.assertNotEqual(new_pair.refresh_token, pair.refresh_token)
        with self.assertRaises(RevokedRefreshToken):
            self.svc.refresh(pair.refresh_token)
        self.svc.refresh(new_pair.refresh_token)  # новый работает

    def test_refresh_unknown_token(self):
        with self.assertRaises(InvalidRefreshToken):
            self.svc.refresh("rt_unknown")

    def test_refresh_expired(self):
        _, pair = self.svc.register("a@b.co", "securePass123")
        self.now += timedelta(days=7, seconds=1)
        with self.assertRaises(InvalidRefreshToken):
            self.svc.refresh(pair.refresh_token)

    def test_refresh_blocked_user(self):
        user, pair = self.svc.register("a@b.co", "securePass123")
        user.is_active = False
        with self.assertRaises(AccountBlocked):
            self.svc.refresh(pair.refresh_token)

    # INT-7
    def test_logout_revokes_refresh(self):
        user, pair = self.svc.register("a@b.co", "securePass123")
        self.svc.logout(user.id, pair.refresh_token)
        with self.assertRaises(RevokedRefreshToken):
            self.svc.refresh(pair.refresh_token)

    def test_logout_without_token_is_ok(self):
        user, _ = self.svc.register("a@b.co", "securePass123")
        self.svc.logout(user.id, None)

    def test_logout_cannot_revoke_foreign_token(self):
        _, pair_a = self.svc.register("a@b.co", "securePass123")
        user_b, _ = self.svc.register("b@b.co", "securePass123")
        self.svc.logout(user_b.id, pair_a.refresh_token)
        self.svc.refresh(pair_a.refresh_token)  # всё ещё действителен


if __name__ == "__main__":
    unittest.main()
