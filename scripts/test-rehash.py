import importlib.util
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location("rehash", Path(__file__).with_name("rehash.py"))
rehash = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rehash)


class DownloadHashTests(unittest.TestCase):
    def test_changes_only_download_hash_and_preserves_formatting(self):
        original = (
            "name = 'same-hash'\r\n"
            "\r\n"
            "[download] # keep this comment\r\n"
            "  hash = 'same-hash' # and this one\r\n"
            "hash-format = 'sha512'\r\n"
            "url = 'https://example.org/same-hash.jar'\r\n"
            "\r\n"
            "[update.custom]\r\n"
            "hash = 'same-hash'\r\n"
        )

        updated = rehash.replace_download_hash(original, "new-hash")

        self.assertEqual(
            updated,
            original.replace("  hash = 'same-hash'", "  hash = 'new-hash'"),
        )

    def test_unsupported_assignment_fails_without_rewriting_other_fields(self):
        original = 'name = "keep"\ndownload = { hash = "old", url = "https://example.org/a" }\n'

        with self.assertRaisesRegex(ValueError, "unambiguous"):
            rehash.replace_download_hash(original, "new")


if __name__ == "__main__":
    unittest.main()
