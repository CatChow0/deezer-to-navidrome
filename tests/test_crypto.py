import base64
import json
import os
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import config, crypto


class Base(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.data = Path(folder.name)
        patches = [mock.patch.object(config, "DATA_DIR", self.data),
                   mock.patch.object(config, "SECRETS_FILE", self.data / "secrets.json"),
                   mock.patch.dict(os.environ, {}, clear=False)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop(crypto.KEY_ENV, None)


class Values(Base):
    def test_round_trip(self):
        value = crypto.encrypt("hunter2-secret")
        self.assertTrue(value.startswith("enc:v1:"))
        self.assertNotIn("hunter2", value)
        self.assertEqual(crypto.decrypt(value), "hunter2-secret")

    def test_two_encryptions_differ(self):
        self.assertNotEqual(crypto.encrypt("same"), crypto.encrypt("same"))

    def test_a_plain_value_passes_through(self):
        self.assertEqual(crypto.decrypt("written-by-an-old-version"), "written-by-an-old-version")
        self.assertEqual(crypto.decrypt(""), "")
        self.assertEqual(crypto.encrypt(""), "")

    def test_a_tampered_value_is_refused(self):
        value = crypto.encrypt("secret")
        raw = bytearray(base64.urlsafe_b64decode(value[7:] + "=" * (-len(value[7:]) % 4)))
        raw[15] ^= 1
        tampered = "enc:v1:" + base64.urlsafe_b64encode(bytes(raw)).decode().rstrip("=")
        with self.assertRaises(crypto.DecryptError):
            crypto.decrypt(tampered)
        with self.assertRaises(crypto.DecryptError):
            crypto.decrypt("enc:v1:short")


class Keys(Base):
    def test_without_the_variable_a_key_file_is_made_once(self):
        crypto.encrypt("x")
        key = crypto.key_file()
        self.assertTrue(key.is_file())
        first = key.read_text()
        crypto.encrypt("y")
        self.assertEqual(key.read_text(), first)
        self.assertEqual(crypto.key_source(), "file")

    def test_the_variable_wins_and_no_file_is_made(self):
        with mock.patch.dict(os.environ, {crypto.KEY_ENV: base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()}):
            value = crypto.encrypt("x")
            self.assertEqual(crypto.decrypt(value), "x")
            self.assertEqual(crypto.key_source(), "env")
        self.assertFalse(crypto.key_file().exists())

    def test_a_passphrase_works_too(self):
        with mock.patch.dict(os.environ, {crypto.KEY_ENV: "a long passphrase someone typed"}):
            self.assertEqual(crypto.decrypt(crypto.encrypt("x")), "x")

    def test_another_key_cannot_read(self):
        with mock.patch.dict(os.environ, {crypto.KEY_ENV: "first key, long enough"}):
            value = crypto.encrypt("x")
        with mock.patch.dict(os.environ, {crypto.KEY_ENV: "second key, long enough"}):
            with self.assertRaises(crypto.DecryptError):
                crypto.decrypt(value)

    def test_setting_the_variable_later_still_reads_old_values(self):
        old = crypto.encrypt("from the file key")
        with mock.patch.dict(os.environ, {crypto.KEY_ENV: "set later, long enough"}):
            self.assertEqual(crypto.decrypt(old), "from the file key")
            self.assertTrue(crypto.needs_rewrap(old))
            self.assertFalse(crypto.needs_rewrap(crypto.encrypt("new")))


class Redact(unittest.TestCase):
    def test_values_and_url_parameters(self):
        text = "POST http://nd/rest/ping?u=bob&t=abc123&s=salt9&apiKey=KEY42 failed for hunter2"
        out = crypto.redact(text, "hunter2")
        for leaked in ("abc123", "salt9", "KEY42", "hunter2"):
            self.assertNotIn(leaked, out)
        self.assertIn("u=bob", out)

    def test_short_or_empty_values_are_ignored(self):
        self.assertEqual(crypto.redact("results=3 ok", "", None, "ab"), "results=3 ok")


class StoredSecrets(Base):
    def test_saved_encrypted_and_read_back(self):
        config.save_secret("deezer_arl", "ARL-SENTINEL-123456")
        raw = config.SECRETS_FILE.read_text()
        self.assertNotIn("ARL-SENTINEL", raw)
        self.assertEqual(config.load_secret("deezer_arl"), "ARL-SENTINEL-123456")

    def test_the_environment_still_wins(self):
        config.save_secret("deezer_arl", "stored")
        with mock.patch.dict(os.environ, {"DEEZER_ARL": "from-env"}):
            self.assertEqual(config.load_secret("deezer_arl"), "from-env")

    def test_old_plain_values_are_read_then_encrypted_at_start(self):
        config.SECRETS_FILE.write_text(json.dumps({"deezer_arl": "OLD-PLAIN-ARL", "api_token": "OLD-TOKEN"}))
        self.assertEqual(config.load_secret("deezer_arl"), "OLD-PLAIN-ARL")
        self.assertEqual(config.encrypt_stored_secrets(), 2)
        raw = config.SECRETS_FILE.read_text()
        self.assertNotIn("OLD-PLAIN-ARL", raw)
        self.assertNotIn("OLD-TOKEN", raw)
        self.assertEqual(config.load_secret("api_token"), "OLD-TOKEN")
        self.assertEqual(config.encrypt_stored_secrets(), 0)

    def test_a_new_key_re_encrypts_what_the_old_one_wrote(self):
        config.save_secret("deezer_arl", "kept across keys")
        with mock.patch.dict(os.environ, {crypto.KEY_ENV: "new key from now on, long"}):
            self.assertEqual(config.encrypt_stored_secrets(), 1)
            crypto.key_file().unlink()
            self.assertEqual(config.load_secret("deezer_arl"), "kept across keys")

    def test_an_unreadable_value_is_kept_and_reads_empty(self):
        with mock.patch.dict(os.environ, {crypto.KEY_ENV: "a key that will be lost, long"}):
            config.save_secret("deezer_arl", "lost")
        with mock.patch.dict(os.environ, {crypto.KEY_ENV: "another key entirely, long"}):
            with self.assertLogs("core.config", level="ERROR"):
                self.assertEqual(config.load_secret("deezer_arl"), "")
            with self.assertLogs("core.config", level="ERROR"):
                self.assertEqual(config.encrypt_stored_secrets(), 0)
            self.assertIn("deezer_arl", json.loads(config.SECRETS_FILE.read_text()))

    def test_removing_a_secret(self):
        config.save_secret("api_token", "x" * 10)
        config.save_secret("api_token", "")
        self.assertEqual(config.load_secret("api_token"), "")
        self.assertNotIn("api_token", json.loads(config.SECRETS_FILE.read_text()))


if __name__ == "__main__":
    unittest.main()
