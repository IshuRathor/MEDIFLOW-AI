import unittest
from unittest.mock import patch

from app.core.security import hash_password, verify_password
from app.core import config


class SecurityTests(unittest.TestCase):
    def test_password_hash_round_trip(self):
        password_hash = hash_password("correct horse battery staple")

        self.assertTrue(verify_password("correct horse battery staple", password_hash))
        self.assertFalse(verify_password("wrong password", password_hash))

    def test_malformed_hash_is_rejected(self):
        self.assertFalse(verify_password("password", "not-a-password-hash"))

    def test_production_config_rejects_missing_jwt_secret(self):
        with patch.object(config, "ENVIRONMENT", "production"):
            with patch.object(config, "JWT_SECRET_KEY", None):
                with self.assertRaisesRegex(RuntimeError, "JWT_SECRET_KEY"):
                    config.validate_startup_config()


if __name__ == "__main__":
    unittest.main()
