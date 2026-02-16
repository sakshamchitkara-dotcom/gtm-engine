import unittest

from gtm.accounts import rollup


def row(email, score, seniority, **kw):
    return {"email": email, "domain": email.split("@")[1], "score": score, "seniority": seniority,
            "owner": "sam@acme.io", "stage": "new", "company": "Acme", "is_free_email": False, **kw}


class AccountsTest(unittest.TestCase):
    def test_rollup(self):
        rows = [row("a@acme.io", 70, "vp", intent=15), row("b@acme.io", 40, "manager"),
                row("c@acme.io", 20, "ic", stage="lost"), row("d@solo.io", 90, "c_level"),
                row("e@gmail.com", 99, "vp", is_free_email=True)]
        accts = {a["domain"]: a for a in rollup(rows)}
        self.assertNotIn("gmail.com", accts)
        acme = accts["acme.io"]
        self.assertEqual((acme["leads"], acme["coverage"], acme["missing"], acme["open"]), (3, 1.0, [], 2))
        self.assertEqual(acme["score"], 70 + 10 + 5)
        self.assertEqual(accts["solo.io"]["missing"], ["champion", "user"])
        self.assertEqual([a["domain"] for a in rollup(rows)], ["solo.io", "acme.io"])
