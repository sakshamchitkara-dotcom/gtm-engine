import csv
import io
import unittest

from gtm import crm

ROW = {"email": "a@x.io", "first_name": "Ana", "last_name": "", "title": "=HYPERLINK(\"evil\")",
       "company": "", "employees": 40, "industry": "saas", "country": "US", "source": "webinar",
       "score": 72, "tier": "B", "owner": "sam@acme.io", "stage": "meeting"}


def parse(fmt):
    buf = io.StringIO()
    crm.export([ROW], fmt, buf)
    return list(csv.DictReader(io.StringIO(buf.getvalue())))[0]


class CRMTest(unittest.TestCase):
    def test_hubspot(self):
        r = parse("hubspot")
        self.assertEqual((r["Lead Status"], r["Lifecycle Stage"], r["Contact owner"]),
                         ("IN_PROGRESS", "salesqualifiedlead", "sam@acme.io"))
        self.assertTrue(r["Job Title"].startswith("'="))

    def test_salesforce_required_fields(self):
        r = parse("salesforce")
        self.assertEqual((r["LastName"], r["Company"], r["Rating"], r["Status"]),
                         ("[not provided]", "[not provided]", "Warm", "Working - Contacted"))

    def test_basic_matches_legacy_export(self):
        self.assertEqual(parse("basic"), {"email": "a@x.io", "score": "72", "tier": "B",
                                          "owner": "sam@acme.io", "stage": "meeting"})
