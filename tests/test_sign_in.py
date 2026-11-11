"""Signing in: any username works, the page after sign-in stays on this site,
and failed attempts from one address cannot lock the owner out."""
import os
import unittest
from unittest import mock

from core import auth

PASSWORD = "long-test-password"


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app

    def setUp(self):
        for name in ("DISABLE_AUTH", "API_TOKEN", "APP_USERNAME", "APP_PASSWORD"):
            os.environ.pop(name, None)
        auth.limiter._entries.clear()
        auth.user_limiter._entries.clear()
        self.addCleanup(auth.limiter._entries.clear)
        self.addCleanup(auth.user_limiter._entries.clear)
        self.client = self.app.test_client()

    def use_account(self, name):
        patcher = mock.patch.dict(os.environ, {"APP_USERNAME": name, "APP_PASSWORD": PASSWORD})
        patcher.start()
        self.addCleanup(patcher.stop)

    def login(self, username, password=PASSWORD, ip="10.0.0.1", **form):
        return self.client.post("/login", data={"username": username, "password": password, **form},
                                environ_base={"REMOTE_ADDR": ip})


class AnyUsername(Base):
    def test_a_name_with_accents_signs_in(self):
        self.use_account("Hélène")
        self.assertEqual(302, self.login("hélène").status_code)

    def test_a_wrong_name_with_accents_is_refused_not_an_error(self):
        self.use_account("admin")
        self.assertEqual(401, self.login("ünknown").status_code)

    def test_the_stored_account_with_accents(self):
        with mock.patch.object(auth, "account_from_env", return_value=False), \
                mock.patch.object(auth, "load_secret", side_effect=lambda n: {
                    "app_username": "José", "app_password_hash": auth.generate_password_hash(PASSWORD)}.get(n, "")):
            self.assertTrue(auth.check_credentials("josé", PASSWORD))
            self.assertFalse(auth.check_credentials("josé", "wrong-password"))
            self.assertFalse(auth.check_credentials("other", PASSWORD))


class NextPage(Base):
    def test_only_a_page_of_this_site(self):
        self.use_account("admin")
        for target, expected in (("/stats", "/stats"), ("//evil.example", "/"), ("/\\evil.example", "/"),
                                 ("/\t/evil.example", "/"), ("https://evil.example", "/")):
            with self.subTest(target=target):
                auth.limiter._entries.clear()
                response = self.login("admin", next=target)
                self.assertEqual(302, response.status_code)
                self.assertEqual(expected, response.headers["Location"])


class FailedAttempts(Base):
    def test_an_address_that_keeps_failing_waits(self):
        self.use_account("admin")
        for _ in range(5):
            self.login("admin", "wrong-password", ip="203.0.113.9")
        self.assertEqual(429, self.login("admin", ip="203.0.113.9").status_code)

    def test_failures_from_elsewhere_do_not_lock_the_owner_out(self):
        self.use_account("admin")
        for _ in range(5):
            self.login("admin", "wrong-password", ip="203.0.113.9")
        self.assertEqual(302, self.login("admin", ip="192.168.1.20").status_code)

    def test_many_failures_on_one_name_from_everywhere_still_wait(self):
        self.use_account("admin")
        for i in range(50):
            self.login("admin", "wrong-password", ip=f"198.51.100.{i}")
        self.assertEqual(429, self.login("admin", ip="192.168.1.20").status_code)

    def test_the_limiter_keeps_a_bounded_number_of_keys(self):
        limiter = auth.LoginLimiter()
        limiter.MAX_KEYS = 50
        for i in range(1200):
            limiter.failure(f"ip:{i}")
        self.assertLessEqual(len(limiter._entries), 50)


class ApiSignOut(Base):
    def test_signing_out_through_the_api_ends_the_web_session(self):
        self.use_account("admin")
        self.login("admin")
        self.assertEqual(200, self.client.get("/api/v1/devices").status_code)
        answer = self.client.post("/api/v1/auth/logout").get_json()
        self.assertEqual({"signed_out": True}, answer)
        self.assertEqual(401, self.client.get("/api/v1/devices").status_code)


class ScrobbleTokens(Base):
    def test_an_address_guessing_tokens_waits(self):
        from routes import listenbrainz

        listenbrainz._limiter._entries.clear()
        self.addCleanup(listenbrainz._limiter._entries.clear)
        for i in range(20):
            self.client.get("/apis/listenbrainz/1/validate-token", headers={"Authorization": f"Token guess-{i}"},
                            environ_base={"REMOTE_ADDR": "203.0.113.7"})
        refused = self.client.get("/apis/listenbrainz/1/validate-token", headers={"Authorization": "Token x"},
                                  environ_base={"REMOTE_ADDR": "203.0.113.7"})
        self.assertEqual(429, refused.status_code)
        other = self.client.get("/apis/listenbrainz/1/validate-token", headers={"Authorization": "Token x"},
                                environ_base={"REMOTE_ADDR": "192.168.1.5"})
        self.assertEqual(200, other.status_code)


class OtherSites(Base):
    def test_a_form_posted_from_another_site_is_refused(self):
        os.environ["DISABLE_AUTH"] = "true"
        self.addCleanup(os.environ.pop, "DISABLE_AUTH", None)
        refused = self.client.post("/admin/clear/library-cache", headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(403, refused.status_code)
        api = self.client.post("/api/v1/settings/clear/library-cache", headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(403, api.status_code)
        self.assertEqual("forbidden", api.get_json()["error"]["code"])

    def test_this_site_and_apps_without_the_header_are_let_through(self):
        os.environ["DISABLE_AUTH"] = "true"
        self.addCleanup(os.environ.pop, "DISABLE_AUTH", None)
        for headers in ({"Sec-Fetch-Site": "same-origin"}, {}):
            with self.subTest(headers=headers):
                self.assertNotEqual(403, self.client.post("/api/v1/auth/logout", headers=headers).status_code)

    def test_a_huge_body_is_refused_before_it_is_read(self):
        self.use_account("admin")
        response = self.client.post("/api/v1/auth/login", data=b"x" * (17 * 1024 * 1024),
                                    content_type="application/json")
        self.assertEqual(413, response.status_code)


if __name__ == "__main__":
    unittest.main()
