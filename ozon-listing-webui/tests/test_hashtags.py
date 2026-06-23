import unittest
from backend.ai_card import clean_hashtags


class CleanHashtagsTest(unittest.TestCase):
    def test_prefixes_hash_and_joins_with_space(self):
        self.assertEqual(clean_hashtags(["женскаясумка", "#кожа"]), "#женскаясумка #кожа")

    def test_underscore_tag_preserved_and_space_dump_split(self):
        # AI 被要求多词用下划线连(无内部空格)→ 原样保留为一个标签
        self.assertEqual(clean_hashtags(["multi_word_tag"]), "#multi_word_tag")
        # 容错:AI 常把多个标签塞进一个串 → 按 # 和空白拆成独立标签
        self.assertEqual(clean_hashtags(["#a #b"]), "#a #b")

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
