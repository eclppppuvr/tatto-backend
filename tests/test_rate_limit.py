import unittest

from app.domain.errors import TooManyAttempts
from app.rate_limit import LoginRateLimiter


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class RateLimiterTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.rl = LoginRateLimiter(max_failures=5, block_seconds=900, clock=self.clock)

    def test_blocks_after_five_failures(self):
        for _ in range(4):
            self.rl.fail("1.1.1.1")
            self.rl.check("1.1.1.1")
        self.rl.fail("1.1.1.1")
        with self.assertRaises(TooManyAttempts):
            self.rl.check("1.1.1.1")

    def test_other_ip_not_affected(self):
        for _ in range(5):
            self.rl.fail("1.1.1.1")
        self.rl.check("2.2.2.2")

    def test_unblocks_after_15_minutes(self):
        for _ in range(5):
            self.rl.fail("1.1.1.1")
        self.clock.t += 901
        self.rl.check("1.1.1.1")

    def test_reset_clears_failures(self):
        for _ in range(4):
            self.rl.fail("1.1.1.1")
        self.rl.reset("1.1.1.1")
        self.rl.fail("1.1.1.1")
        self.rl.check("1.1.1.1")

    def test_old_failures_expire(self):
        for _ in range(4):
            self.rl.fail("1.1.1.1")
        self.clock.t += 1000
        self.rl.fail("1.1.1.1")
        self.rl.check("1.1.1.1")


if __name__ == "__main__":
    unittest.main()
