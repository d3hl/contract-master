import unittest
from tags import normalize_tags


class TagsTests(unittest.TestCase):
    def test_strip_casefold_and_deduplicate_in_order(self):
        self.assertEqual(normalize_tags([" Alpha ", "BETA", "alpha", " beta ", "Gamma"]), ["alpha", "beta", "gamma"])

    def test_unicode_casefold(self):
        self.assertEqual(normalize_tags([" Straße ", "STRASSE"]), ["strasse"])

    def test_empty_list(self):
        self.assertEqual(normalize_tags([]), [])

    def test_input_not_mutated(self):
        source = [" X ", "x"]
        self.assertEqual(normalize_tags(source), ["x"])
        self.assertEqual(source, [" X ", "x"])

    def test_non_list_rejected(self):
        for value in (None, "alpha", ("alpha",), 2):
            with self.subTest(value=value):
                with self.assertRaises(TypeError): normalize_tags(value)

    def test_non_string_member_rejected(self):
        for value in (1, True, None, 1.5):
            with self.subTest(value=value):
                with self.assertRaises(TypeError): normalize_tags(["valid", value])

    def test_blank_member_rejected(self):
        for value in ("", " ", "\t\n"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError): normalize_tags(["valid", value])
