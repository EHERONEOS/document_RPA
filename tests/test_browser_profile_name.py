from types import SimpleNamespace
import unittest

from app.core.browser.session_lock import build_browser_profile_name


def build_context(website_info, carrier_code="ZIM"):
    return SimpleNamespace(website_info=website_info, carrier_code=carrier_code)


class BrowserProfileNameTests(unittest.TestCase):
    def test_browser_profile_name_uses_website_info_id_and_carrier(self):
        context = build_context(
            {
                "id": 1001,
                "websiteUserName": "operator",
                "websiteAccount": "shared-account",
            }
        )

        self.assertEqual(build_browser_profile_name(context), "1001_ZIM")

    def test_same_account_different_website_info_id_uses_different_profile(self):
        first_role = build_context({"id": "role-a", "websiteAccount": "shared-account"})
        second_role = build_context({"id": "role-b", "websiteAccount": "shared-account"})

        self.assertEqual(build_browser_profile_name(first_role), "role-a_ZIM")
        self.assertEqual(build_browser_profile_name(second_role), "role-b_ZIM")

    def test_missing_website_info_id_falls_back_to_default(self):
        context = build_context({"websiteAccount": "shared-account"})

        self.assertEqual(build_browser_profile_name(context), "default_ZIM")


if __name__ == "__main__":
    unittest.main()
