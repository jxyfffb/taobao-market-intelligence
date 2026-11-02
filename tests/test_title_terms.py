import unittest


class TitleTermTests(unittest.TestCase):
    def test_classifies_eight_term_categories_with_title_frequency(self):
        from src.market_analysis import classify_market_title_terms

        classification = classify_market_title_terms(
            [
                "苹果15ProMax液态硅胶手机壳防摔磁吸女生夏季简约高级感",
                "iPhone15 Pro Max硅胶保护套防摔女士户外简约",
                "华为Mate60金属手机壳商务男士全包",
            ]
        )

        self.assertEqual(classification["sample_title_count"], 3)
        self.assertEqual(classification["missing_title_count"], 0)
        categories = classification["categories"]
        self.assertEqual(
            {"手机壳": 2, "保护套": 1},
            self.term_counts(categories["product"]),
        )
        self.assertEqual(2, self.term_counts(categories["function"])["防摔"])
        self.assertEqual(1, self.term_counts(categories["function"])["磁吸"])
        self.assertEqual(
            {"液态硅胶": 1, "硅胶": 1, "金属": 1},
            self.term_counts(categories["material"]),
        )
        self.assertEqual(2, self.term_counts(categories["specification"])["15 Pro Max"])
        self.assertEqual(1, self.term_counts(categories["audience"])["女士"])
        self.assertEqual(1, self.term_counts(categories["audience"])["男士"])
        self.assertEqual(1, self.term_counts(categories["scenario"])["夏季"])
        self.assertEqual(1, self.term_counts(categories["scenario"])["商务"])
        self.assertEqual(2, self.term_counts(categories["style"])["简约"])
        self.assertEqual(2, self.term_counts(categories["brand"])["苹果"])
        self.assertEqual(1, self.term_counts(categories["brand"])["华为"])

    def test_longest_overlapping_term_wins_within_each_category(self):
        from src.market_analysis import classify_market_title_terms

        classification = classify_market_title_terms(
            ["液态硅胶手机保护套女士超薄", "硅胶保护套女"]
        )
        categories = classification["categories"]

        self.assertEqual(
            {"液态硅胶": 1, "硅胶": 1},
            self.term_counts(categories["material"]),
        )
        self.assertEqual(
            {"手机保护套": 1, "保护套": 1},
            self.term_counts(categories["product"]),
        )
        self.assertEqual(
            {"女士": 1, "女": 1},
            self.term_counts(categories["audience"]),
        )

    def test_unknown_and_missing_titles_are_not_forced_into_categories(self):
        from src.market_analysis import classify_market_title_terms

        classification = classify_market_title_terms([None, "", "神秘款式XYZ"])

        self.assertEqual(1, classification["sample_title_count"])
        self.assertEqual(2, classification["missing_title_count"])
        self.assertTrue(
            all(not terms for terms in classification["categories"].values())
        )

    def test_invalid_title_boundary_fails_with_received_value(self):
        from src.market_analysis import classify_market_title_terms

        with self.assertRaisesRegex(ValueError, r"product_titles must be a list: actual='bad'"):
            classify_market_title_terms("bad")
        with self.assertRaisesRegex(ValueError, r"product title must be text or None: index=1 actual=7"):
            classify_market_title_terms(["手机壳", 7])

    @staticmethod
    def term_counts(term_statistics):
        return {
            term_statistic["term"]: term_statistic["title_count"]
            for term_statistic in term_statistics
        }


if __name__ == "__main__":
    unittest.main()
