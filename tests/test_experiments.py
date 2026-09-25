import unittest
from collections import Counter

from gtm import experiments
from gtm.models import Lead
from gtm.sequences import build


class ExperimentsTest(unittest.TestCase):
    def test_assignment_is_stable_and_balanced(self):
        self.assertEqual(experiments.arm("A@x.io"), experiments.arm("a@x.io"))
        split = Counter(experiments.arm(f"user{i}@x.io") for i in range(2000))
        self.assertLess(abs(split["control"] - split["challenger"]), 150)

    def test_subject_follows_arm(self):
        for i in range(10):
            lead = Lead(email=f"p{i}@co.io", first_name="Pat", company="Co", tier="B", owner="sam@acme.io")
            want = "idea for Co" if experiments.arm(lead.email) == "control" else "Co's speed-to-lead"
            self.assertEqual(build(lead)[0]["subject"], want)
        self.assertIsNone(experiments.subject(Lead(email="c@co.io", tier="C")))

    def test_z_test(self):
        z, p = experiments.z_test(60, 500, 40, 500)   # 12% vs 8%
        self.assertAlmostEqual(z, 2.108, places=3)  # pooled p=.1, se=.01897
        self.assertAlmostEqual(p, 0.0350, places=4)
        self.assertEqual(experiments.z_test(0, 0, 5, 10), (0.0, 1.0))
        self.assertEqual(experiments.z_test(0, 10, 0, 10), (0.0, 1.0))

    def test_results(self):
        rows = [{"email": f"u{i}@x.io", "tier": "A", "stage": "replied" if i % 3 == 0 else "contacted"}
                for i in range(30)] + [{"email": "n@x.io", "tier": "A", "stage": "new"}]
        res = experiments.results(rows)
        self.assertEqual(sum(n for _, n in res["arms"].values()), 30)
        self.assertEqual(sum(s for s, _ in res["arms"].values()), 10)
