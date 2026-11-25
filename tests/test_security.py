import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from app.domain.entities import Role
from app.domain.errors import InvalidAccessToken
from app.security import (BcryptHasher, create_access_token, decode_access_token,
                          hash_refresh_token, new_refresh_token)

SECRET = "x" * 32

try:
    import bcrypt  # noqa: F401
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False


class AccessTokenTests(unittest.TestCase):
    def test_roundtrip(self):
        uid = uuid4()
        token = create_access_token(uid, Role.MASTER, SECRET, 15, datetime.now(timezone.utc))
        claims = decode_access_token(token, SECRET)
        self.assertEqual(claims.user_id, uid)
        self.assertEqual(claims.role, Role.MASTER)

    def test_expired(self):
        old = datetime.now(timezone.utc) - timedelta(hours=1)
        token = create_access_token(uuid4(), Role.CLIENT, SECRET, 15, old)
        with self.assertRaises(InvalidAccessToken):
            decode_access_token(token, SECRET)

    def test_wrong_secret(self):
        token = create_access_token(uuid4(), Role.CLIENT, SECRET, 15, datetime.now(timezone.utc))
        with self.assertRaises(InvalidAccessToken):
            decode_access_token(token, "y" * 32)

    def test_garbage(self):
        with self.assertRaises(InvalidAccessToken):
            decode_access_token("not-a-jwt", SECRET)

    def test_not_access_type(self):
        now = int(datetime.now(timezone.utc).timestamp())
        token = jwt.encode({"sub": str(uuid4()), "type": "refresh", "exp": now + 60}, SECRET, algorithm="HS256")
        with self.assertRaises(InvalidAccessToken):
            decode_access_token(token, SECRET)

    def test_alg_none_rejected(self):
        now = int(datetime.now(timezone.utc).timestamp())
        token = jwt.encode({"sub": str(uuid4()), "type": "access", "exp": now + 60}, None, algorithm="none")
        with self.assertRaises(InvalidAccessToken):
            decode_access_token(token, SECRET)


class RefreshTokenTests(unittest.TestCase):
    def test_format_and_uniqueness(self):
        a, b = new_refresh_token(), new_refresh_token()
        self.assertTrue(a.startswith("rt_"))
        self.assertNotEqual(a, b)

    def test_hash_is_stable_sha256(self):
        self.assertEqual(hash_refresh_token("rt_abc"), hash_refresh_token("rt_abc"))
        self.assertEqual(len(hash_refresh_token("rt_abc")), 64)
        self.assertNotEqual(hash_refresh_token("rt_abc"), "rt_abc")


@unittest.skipUnless(HAS_BCRYPT, "bcrypt не установлен")
class BcryptTests(unittest.TestCase):
    def test_hash_verify(self):
        h = BcryptHasher(rounds=4)
        hashed = h.hash("securePass123")
        self.assertNotIn("securePass123", hashed)
        self.assertTrue(h.verify("securePass123", hashed))
        self.assertFalse(h.verify("wrong", hashed))

    def test_long_unicode_password(self):
        h = BcryptHasher(rounds=4)
        pwd = "пароль" * 40
        self.assertTrue(h.verify(pwd, h.hash(pwd)))


if __name__ == "__main__":
    unittest.main()
