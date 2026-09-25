import random
import unittest

from gtm import calibrate
from gtm.enrich import enrich
from gtm.models import Lead
from gtm.scoring import load_config, score


def rows(n=400, seed=1):
    """Leads where fintech wins 75% and everything else 20%, whatever icp.json says."""
    rng, cfg, out = random.Random(seed), load_config(), []
    for i in range(n):
        lead = enrich(Lead(email=f"p{i}@c{i}.io", title=rng.choice(["VP Sales", "Analyst", "Director"]),
                           employees=rng.choice([30, 120, 5000]), country="US", source="list",
                           industry=rng.choice(["fintech", "saas", "software"])))
        score(lead, cfg)
        r = lead.to_dict()
        r["stage"] = "won" if rng.random() < (0.75 if lead.industry == "fintech" else 0.2) else "lost"
        out.append(r)
    return out


class CalibrateTest(unittest.TestCase):
    def test_auc(self):
        self.assertEqual(calibrate.auc([3, 2, 1], [1, 0, 0]), 1.0)
        self.assertEqual(calibrate.auc([1, 1], [1, 0]), 0.5)
        self.assertIsNone(calibrate.auc([1, 2], [0, 0]))

    def test_finds_the_real_driver_and_keeps_tier_sizes(self):
        data, cfg = rows(), load_config()
        res = calibrate.calibrate(data, cfg)
        self.assertEqual(res["table"][0]["feature"], "industries:fintech")
        self.assertGreater(res["auc_model"], res["auc_current"] + 0.1)
        new = res["config"]
        self.assertGreater(new["industries"]["fintech"], new["industries"]["saas"])
        self.assertEqual(cfg["industries"]["saas"], 25)  # input config untouched
        # rescoring with the calibrated config keeps each tier's headcount (within ties)
        rescored = [score(enrich(Lead(**{k: r[k] for k in ("email", "title", "employees", "industry",
                                                              "country", "source")})), new) for r in data]
        for t in "ABC":
            before = sum(r["tier"] == t for r in data)
            self.assertLess(abs(sum(l.tier == t for l in rescored) - before), 0.1 * len(data), t)
        self.assertGreater(calibrate.auc([l.score for l in rescored], [r["stage"] == "won" for r in data]),
                           res["auc_current"] + 0.1)

    def test_needs_both_outcomes(self):
        with self.assertRaises(ValueError):
            calibrate.calibrate([dict(r, stage="won") for r in rows(20)], load_config())


if __name__ == "__main__":
    unittest.main()
