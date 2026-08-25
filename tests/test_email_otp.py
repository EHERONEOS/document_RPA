import unittest
from unittest.mock import Mock, patch

from app.core.integrations.email_otp import read_latest_otp
from app.core.task.errors import LoginError


class EmailOtpTests(unittest.TestCase):
    def test_missing_imap_host_is_a_login_error(self):
        with self.assertRaisesRegex(LoginError, "IMAP 主机"):
            read_latest_otp("", "account", "password", subject_marker="Verification code")

    @patch("app.core.integrations.email_otp.imaplib.IMAP4_SSL")
    def test_reads_latest_matching_six_digit_code(self, imap_client_class):
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        client.search.return_value = ("OK", [b"1 2"])
        client.fetch.side_effect = [
            ("OK", [(b"2", b"Subject: Verification code\n\nYour verification code is 654321")]),
        ]
        imap_client_class.return_value = client

        code = read_latest_otp("imap.example.test", "account", "password", subject_marker="Verification code")

        self.assertEqual("654321", code)
        client.login.assert_called_once_with("account", "password")


if __name__ == "__main__":
    unittest.main()
