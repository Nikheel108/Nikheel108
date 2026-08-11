import unittest

from scripts.generate_profile_visual import get_token


class TokenResolutionTests(unittest.TestCase):
    def test_prefers_personal_token_when_available(self):
        env = {"PERSONAL_TOKEN": "pat", "GITHUB_TOKEN": "gh", "GH_TOKEN": "gh2"}
        self.assertEqual(get_token(env), "pat")

    def test_falls_back_to_github_token(self):
        env = {"GITHUB_TOKEN": "gh"}
        self.assertEqual(get_token(env), "gh")

    def test_falls_back_to_gh_token(self):
        env = {"GH_TOKEN": "gh2"}
        self.assertEqual(get_token(env), "gh2")


if __name__ == "__main__":
    unittest.main()
