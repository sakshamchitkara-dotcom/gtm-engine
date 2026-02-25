import unittest

from gtm.forecast import forecast


class ForecastTest(unittest.TestCase):
    def test_weighted_by_stage_and_size(self):
        rows = [
            {"owner": "sam", "stage": "opportunity", "size_band": "mid"},        # 20k * .4 = 8000
            {"owner": "sam", "stage": "meeting", "size_band": "enterprise"},     # 120k * .2 = 24000
            {"owner": "sam", "stage": "lost", "size_band": "enterprise"},
            {"owner": "maya", "stage": "won", "size_band": "upper_mid"},
            {"owner": "maya", "stage": "new", "size_band": None},                # unknown 5k * .02 = 100
        ]
        f = {o["owner"]: o for o in forecast(rows)}
        self.assertEqual((f["sam"]["open_acv"], f["sam"]["weighted"], f["sam"]["leads"]), (140_000, 32_000, 3))
        self.assertEqual((f["maya"]["won"], f["maya"]["weighted"]), (45_000, 100))
        self.assertEqual(f["TOTAL"]["weighted"], 32_100)
        self.assertEqual([o["owner"] for o in forecast(rows)], ["sam", "maya", "TOTAL"])
