import unittest
from backend.ai_card import clean_hashtags


class CleanHashtagsTest(unittest.TestCase):
    def test_prefixes_hash_and_joins_with_space(self):
        self.assertEqual(clean_hashtags(["женскаясумка", "#кожа"]), "#женскаясумка #кожа")

    def test_multiword_to_underscore(self):
        self.assertEqual(clean_hashtags(["multi word tag"]), "#multi_word_tag")

    def test_dedup(self):
        self.assertEqual(clean_hashtags(["#x", "x", "  x "]), "#x")

    def test_limit_30(self):
        out = clean_hashtags([f"t{i}" for i in range(40)])
        self.assertEqual(len(out.split(" ")), 30)

    def test_empty(self):
        self.assertEqual(clean_hashtags([]), "")
        self.assertEqual(clean_hashtags(["", "  ", "#"]), "")


if __name__ == "__main__":
    unittest.main()
