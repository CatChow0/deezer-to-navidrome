import socket
import unittest

from core import subsonic
from tests.fake_subsonic import FakeSubsonic

SECRET = "pw-SENTINEL-4242"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Client(unittest.TestCase):
    def setUp(self):
        self.server = FakeSubsonic().start()
        self.addCleanup(self.server.stop)
        self.server.add_user("alice", SECRET, admin=True, api_key="KEY-SENTINEL-777", folders=(1, 2))
        self.server.add_user("bob", "bobpass", folders=(1,))
        self.server.folders[2] = "Podcasts"

    def client(self, user="alice", secret=SECRET, auth="password"):
        return subsonic.Client(self.server.url, user, auth, secret)

    def test_password_through_a_token_and_never_in_the_url(self):
        self.client().ping()
        self.client().user()
        for req in self.server.requests:
            self.assertEqual(req["method"], "POST")
            self.assertEqual(req["query"], "")
            self.assertIn("t", req["form"])
            self.assertNotIn("p", req["form"])

    def test_wrong_password(self):
        with self.assertRaises(subsonic.SubsonicError) as caught:
            self.client(secret="nope").ping()
        self.assertEqual(caught.exception.code, 40)
        self.assertEqual(caught.exception.message, "Wrong user name or password.")

    def test_api_key(self):
        self.client(user="alice", secret="KEY-SENTINEL-777", auth="apikey").ping()
        sent = self.server.requests[-1]["form"]
        self.assertIn("apiKey", sent)
        self.assertNotIn("u", sent)
        with self.assertRaises(subsonic.SubsonicError) as caught:
            self.client(secret="wrong-key", auth="apikey").ping()
        self.assertEqual(caught.exception.code, 44)

    def test_rights_and_libraries(self):
        self.assertTrue(self.client().user()["adminRole"])
        self.assertFalse(self.client("bob", "bobpass").user()["adminRole"])
        self.assertEqual([f["name"] for f in self.client().music_folders()], ["Music", "Podcasts"])
        self.assertEqual([f["name"] for f in self.client("bob", "bobpass").music_folders()], ["Music"])

    def test_extensions(self):
        self.assertIn("apiKeyAuthentication", self.client().extensions())

    def test_a_server_without_form_post_gets_a_query(self):
        self.server.accept_post = False
        self.client().ping()
        self.assertEqual([r["method"] for r in self.server.requests[-2:]], ["POST", "GET"])

    def test_lists_go_as_repeated_parameters(self):
        self.server.add_song("s1", "One", "A")
        self.server.add_song("s2", "Two", "A")
        body = self.client().call("createPlaylist", name="Mix", songId=["s1", "s2"])
        self.assertEqual([e["id"] for e in body["playlist"]["entry"]], ["s1", "s2"])


class Failures(unittest.TestCase):
    def test_unreachable_server_says_where_without_secrets(self):
        url = f"http://127.0.0.1:{free_port()}/navidrome"
        with self.assertRaises(subsonic.SubsonicError) as caught:
            subsonic.Client(url, "alice", "password", SECRET, timeout=2).ping()
        self.assertEqual(caught.exception.code, 0)
        self.assertIn("127.0.0.1", caught.exception.message)
        self.assertNotIn(SECRET, caught.exception.message)

    def test_not_a_subsonic_server(self):
        server = FakeSubsonic().start()
        self.addCleanup(server.stop)
        with self.assertRaises(subsonic.SubsonicError) as caught:
            subsonic.Client(server.url + "/wrong", "a", "password", "b").ping()
        self.assertIn("No Subsonic API", caught.exception.message)

    def test_no_address(self):
        with self.assertRaises(subsonic.SubsonicError):
            subsonic.Client("", "a", "password", "b").ping()


class ConnectionTest(unittest.TestCase):
    def setUp(self):
        self.server = FakeSubsonic().start()
        self.addCleanup(self.server.stop)
        self.server.add_user("alice", SECRET, admin=False)

    def test_everything_learnt(self):
        result = subsonic.test_connection(self.server.url, "alice", "password", SECRET)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["server_version"], "0.64.0 (fake)")
        self.assertIs(result["admin"], False)
        self.assertEqual(result["libraries"], [{"id": 1, "name": "Music"}])
        self.assertTrue(result["api_keys"])
        self.assertTrue(result["open_subsonic"])

    def test_failure_is_a_result_not_an_exception(self):
        result = subsonic.test_connection(self.server.url, "alice", "password", "wrong")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "Wrong user name or password.")

    def test_a_server_without_extensions(self):
        self.server.extensions = []
        self.server.open_subsonic = False
        result = subsonic.test_connection(self.server.url, "alice", "password", SECRET)
        self.assertTrue(result["ok"])
        self.assertFalse(result["api_keys"])


if __name__ == "__main__":
    unittest.main()
