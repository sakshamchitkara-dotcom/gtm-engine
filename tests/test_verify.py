import unittest

from gtm.verify import verify


class VerifyTest(unittest.TestCase):
    def test_statuses(self):
        self.assertEqual(verify("priya@northwind.io"), ("valid", ""))
        self.assertEqual(verify("Priya@Northwind.IO")[0], "valid")
        self.assertEqual(verify("sales@northwind.io"), ("risky", "role-based address"))
        self.assertEqual(verify("x@mailinator.com"), ("invalid", "disposable domain"))
        self.assertEqual(verify("jo@gmial.com"), ("invalid", "typo domain, did you mean gmail.com"))
        for bad in ["", "a@b", "a..b@x.com", "a@-x.com", "no-at.com", "a b@x.com"]:
            self.assertEqual(verify(bad)[0], "invalid", bad)
