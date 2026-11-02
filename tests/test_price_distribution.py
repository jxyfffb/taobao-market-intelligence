import unittest


def product(item_id, price, payment_text=None, shop_name="样本店铺"):
    return {
        "item_id": item_id,
        "display_rank": int(item_id) if item_id.isdigit() else 1,
        "title": f"商品 {item_id}",
        "shop_name": shop_name,
        "display_price": price,
        "payment_text": payment_text,
    }


class PricePaymentDistributionTests(unittest.TestCase):
    def test_distribution_keeps_missing_heat_separate_and_clusters_identical_points(self):
        from src.market_analysis import calculate_price_payment_distribution

        distribution = calculate_price_payment_distribution(
            [
                product("1", "99", "100+人付款", "甲店"),
                product("2", "99", "100+人付款", "乙店"),
                product("3", "99", "100+人付款", "乙店"),
                product("4", "129", "1万+人付款", "丙店"),
                product("5", "159", None, "丁店"),
                product("6", "价格待确认", "300+人付款", "戊店"),
            ]
        )

        self.assertEqual(6, distribution["sample_count"])
        self.assertEqual(
            {
                "valid_count": 5,
                "missing_or_invalid_count": 1,
                "minimum": 99.0,
                "median": 99.0,
                "maximum": 159.0,
            },
            distribution["price"],
        )
        self.assertEqual(
            {"known_count": 4, "missing_count": 1, "coverage_percent": 80.0},
            distribution["payment_heat"],
        )
        self.assertEqual(
            {
                "minimum": 99.0,
                "maximum": 129.0,
                "product_count": 4,
                "shop_count": 3,
            },
            distribution["mainstream_price_band"],
        )

        clustered = next(
            cluster
            for cluster in distribution["clusters"]
            if cluster["price"] == 99.0 and cluster["payment_heat_lower_bound"] == 100
        )
        self.assertEqual(3, clustered["product_count"])
        self.assertEqual(2, clustered["shop_count"])
        self.assertEqual(["1", "2", "3"], clustered["item_ids"])

        missing_heat = next(
            cluster
            for cluster in distribution["clusters"]
            if cluster["payment_heat_lower_bound"] is None
        )
        self.assertEqual(159.0, missing_heat["price"])
        self.assertEqual(["5"], missing_heat["item_ids"])

    def test_same_price_summary_distinguishes_products_from_shops(self):
        from src.market_analysis import calculate_price_payment_distribution

        distribution = calculate_price_payment_distribution(
            [
                product("1", "88", "10+人付款", "同一家店"),
                product("2", "88", "20+人付款", "同一家店"),
                product("3", "88", "30+人付款", "同一家店"),
                product("4", "108", "40+人付款", "另一家店"),
            ]
        )

        self.assertEqual(
            {
                "price": 88.0,
                "product_count": 3,
                "shop_count": 1,
                "item_ids": ["1", "2", "3"],
            },
            distribution["same_price_groups"][0],
        )


if __name__ == "__main__":
    unittest.main()
