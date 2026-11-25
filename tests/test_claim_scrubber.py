import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gen_sample_claims
from claim_scrubber import load_claims, scrub, summarize, detect_duplicates
from scrub_rules import Claim, npi_valid, scrub_claim
from dashboard import render

TODAY = date.today()


def base_claim(**kw):
    defaults = dict(
        claim_id="C1", patient_id="P1", patient_dob="1980-01-15", patient_sex="M",
        subscriber_id="S1", payer="Aetna", dos=(TODAY - timedelta(days=10)).isoformat(),
        pos="11", rendering_npi="1234567893", cpt="99213", modifier="",
        icd10_codes=["M54.5"], units=1, billed_amount=150.0,
    )
    defaults.update(kw)
    return Claim(**defaults)


class ScrubberTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.csv_path = os.path.join(cls.tmp, "claims.csv")
        rows = gen_sample_claims.generate(85)
        import csv as csv_mod
        with open(cls.csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv_mod.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        cls.claims = load_claims(cls.csv_path)
        cls.results = scrub(cls.claims, TODAY)
        cls.summary = summarize(cls.results)

    def test_npi_luhn(self):
        self.assertTrue(npi_valid("1234567893"))  # known-valid test NPI
        self.assertFalse(npi_valid("1234567890"))
        self.assertFalse(npi_valid("123"))
        self.assertFalse(npi_valid("abcdefghij"))

    def test_clean_claim_passes(self):
        self.assertEqual(scrub_claim(base_claim(), TODAY), [])

    def test_missing_fields(self):
        findings = scrub_claim(base_claim(subscriber_id=""), TODAY)
        self.assertTrue(any(f.rule_id == "REQ" for f in findings))

    def test_future_dos(self):
        future = (TODAY + timedelta(days=3)).isoformat()
        findings = scrub_claim(base_claim(dos=future), TODAY)
        self.assertTrue(any(f.rule_id == "DATE" and f.severity == "error" for f in findings))

    def test_timely_filing(self):
        old = (TODAY - timedelta(days=200)).isoformat()
        findings = scrub_claim(base_claim(dos=old, payer="Aetna"), TODAY)
        self.assertTrue(any(f.rule_id == "TF" and f.severity == "error" for f in findings))
        near = (TODAY - timedelta(days=165)).isoformat()
        findings = scrub_claim(base_claim(dos=near, payer="Cigna"), TODAY)
        self.assertTrue(any(f.rule_id == "TF" and f.severity == "warning" for f in findings))

    def test_bundling(self):
        c = base_claim(cpt="82040")
        c.same_day_cpts = ["80053"]
        findings = scrub_claim(c, TODAY)
        self.assertTrue(any(f.rule_id == "NCCI" for f in findings))
        c2 = base_claim(cpt="82040", modifier="59")
        c2.same_day_cpts = ["80053"]
        findings = scrub_claim(c2, TODAY)
        self.assertFalse(any(f.rule_id == "NCCI" for f in findings))

    def test_pos_inpatient_only(self):
        findings = scrub_claim(base_claim(cpt="29881", pos="11"), TODAY)
        self.assertTrue(any(f.rule_id == "POS" for f in findings))

    def test_sex_conflict(self):
        findings = scrub_claim(base_claim(cpt="55700", patient_sex="F"), TODAY)
        self.assertTrue(any(f.rule_id == "SEX" for f in findings))

    def test_cob(self):
        findings = scrub_claim(base_claim(payer_sequence="secondary"), TODAY)
        self.assertTrue(any(f.rule_id == "COB" for f in findings))
        findings = scrub_claim(base_claim(payer_sequence="secondary", primary_paid_amount=100.0), TODAY)
        self.assertFalse(any(f.rule_id == "COB" for f in findings))

    def test_lcd_medical_necessity(self):
        findings = scrub_claim(base_claim(cpt="82306", icd10_codes=["J02.9"]), TODAY)
        self.assertTrue(any(f.rule_id == "LCD" for f in findings))
        findings = scrub_claim(base_claim(cpt="82306", icd10_codes=["E55.9"]), TODAY)
        self.assertFalse(any(f.rule_id == "LCD" for f in findings))

    def test_icd_exclusions(self):
        findings = scrub_claim(base_claim(icd10_codes=["B96.20", "N39.0"]), TODAY)
        self.assertTrue(any(f.rule_id == "ICDX" and f.severity == "error" for f in findings))
        findings = scrub_claim(base_claim(icd10_codes=["I10", "I11.0"]), TODAY)
        self.assertTrue(any(f.rule_id == "ICDX" and f.severity == "warning" for f in findings))
        findings = scrub_claim(base_claim(icd10_codes=["I10", "E11.9"]), TODAY)
        self.assertFalse(any(f.rule_id == "ICDX" for f in findings))

    def test_i10_not_flagged_for_specificity(self):
        findings = scrub_claim(base_claim(icd10_codes=["I10"]), TODAY)
        self.assertFalse(any(f.rule_id == "CODE" for f in findings))

    def test_sample_data_flags_expected_rules(self):
        rule_ids = {f.rule_id for r in self.results for f in r["findings"]}
        for expected in ("REQ", "NPI", "DATE", "TF", "CODE", "MOD", "NCCI", "POS",
                         "UNIT", "CHG", "SEX", "COB", "DUP", "LCD", "ICDX"):
            self.assertIn(expected, rule_ids, f"rule {expected} never fired on sample data")

    def test_summary_math(self):
        s = self.summary
        self.assertEqual(s["claims_scrubbed"], 85)
        self.assertEqual(s["clean_claims"] + s["claims_flagged"], 85)
        self.assertGreater(s["clean_rate_pct"], 40)
        self.assertGreater(s["billed_at_risk"], 0)
        self.assertTrue(s["findings_by_rule"])

    def test_duplicates_detected(self):
        dupes = detect_duplicates(self.claims)
        self.assertTrue(dupes)

    def test_dashboard_render(self):
        payload = {"summary": self.summary,
                   "claims": [{"claim_id": "C1", "payer": "Aetna", "cpt": "99213",
                               "billed_amount": 150.0,
                               "findings": [{"rule_id": "TF", "severity": "error",
                                             "message": "past filing limit"}]}]}
        page = render(payload)
        self.assertIn("Codifyre AI", page)
        self.assertIn('id="theme-toggle"', page)
        self.assertIn("body.light", page)
        self.assertIn("Findings by rule", page)


if __name__ == "__main__":
    unittest.main()
