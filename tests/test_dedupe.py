import unittest

from gtm.dedupe import cluster_companies, dedupe, normalize_company
from gtm.models import Lead


class DedupeTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_company("Acme, Inc."), "acme")
        self.assertEqual(normalize_company("ACME GmbH"), "acme")
        self.assertEqual(normalize_company("Smith & Co Ltd"), "smith and")

    def test_cluster_picks_most_common_spelling(self):
        m = cluster_companies(["Northwind", "Northwind Inc", "Northwind", "Nortwind LLC", "Ledgerly"])
        self.assertEqual({m["Northwind Inc"], m["Nortwind LLC"], m["Northwind"]}, {"Northwind"})
        self.assertEqual(m["Ledgerly"], "Ledgerly")

    def test_person_dupes_by_name_and_domain(self):
        leads = [Lead(email="john.smith@acme.io", first_name="John", last_name="Smith", company="Acme Inc"),
                 Lead(email="jsmith@acme.io", first_name="john", last_name="smith", company="ACME"),
                 Lead(email="john@other.io", first_name="John", last_name="Smith", company="Other"),
                 Lead(email="x@acme.io", company="Acme")]
        kept, dropped = dedupe(leads)
        self.assertEqual(dropped, 1)
        self.assertEqual([l.email for l in kept], ["john.smith@acme.io", "john@other.io", "x@acme.io"])
        self.assertEqual({kept[0].company, kept[2].company}, {"Acme Inc"})
