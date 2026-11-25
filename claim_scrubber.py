#!/usr/bin/env python3
"""Codifyre AI - Clean Claim Pre-Submission Scrubber.

Scrub claims BEFORE submission: missing fields, bad NPIs, invalid codes,
timely-filing windows, NCCI-style bundling conflicts, POS/code mismatches,
modifier problems, COB gaps. Console report, JSON, findings CSV, and an
HTML dashboard.

Usage:
    python claim_scrubber.py data/sample_claims.csv
    python claim_scrubber.py data/sample_claims.csv --json scrub_report.json \
        --findings findings.csv
    python dashboard.py scrub_report.json -o dashboard.html
"""

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date

from scrub_rules import Claim, scrub_claim

EXPECTED = [
    "claim_id", "patient_id", "patient_dob", "patient_sex", "subscriber_id",
    "payer", "dos", "pos", "rendering_npi", "cpt", "modifier", "icd10_codes",
    "units", "billed_amount", "payer_sequence", "primary_paid_amount",
]


def load_claims(path):
    claims = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for col in ("claim_id", "payer", "dos", "cpt"):
            if col not in (reader.fieldnames or []):
                raise ValueError(f"CSV is missing required column: {col}")
        for i, row in enumerate(reader, start=2):
            try:
                claims.append(Claim(
                    claim_id=row["claim_id"].strip(),
                    patient_id=row.get("patient_id", "").strip(),
                    patient_dob=row.get("patient_dob", "").strip(),
                    patient_sex=row.get("patient_sex", "").strip(),
                    subscriber_id=row.get("subscriber_id", "").strip(),
                    payer=row["payer"].strip(),
                    dos=row["dos"].strip(),
                    pos=row.get("pos", "").strip(),
                    rendering_npi=row.get("rendering_npi", "").strip(),
                    cpt=row["cpt"].strip(),
                    modifier=row.get("modifier", "").strip(),
                    icd10_codes=[d.strip() for d in (row.get("icd10_codes") or "").split(";") if d.strip()],
                    units=float(row.get("units") or 0),
                    billed_amount=float(row.get("billed_amount") or 0),
                    payer_sequence=(row.get("payer_sequence") or "primary").strip(),
                    primary_paid_amount=(float(row["primary_paid_amount"])
                                         if (row.get("primary_paid_amount") or "").strip() else None),
                ))
            except ValueError as exc:
                raise ValueError(f"Row {i}: bad data ({exc})") from exc
    # same-day companion codes per patient, for bundling checks
    by_pd = defaultdict(list)
    for c in claims:
        by_pd[(c.patient_id, c.dos)].append(c.cpt)
    for c in claims:
        c.same_day_cpts = [x for x in by_pd[(c.patient_id, c.dos)] if x != c.cpt]
    return claims


def detect_duplicates(claims):
    """Same patient + DOS + CPT appearing more than once in the batch."""
    seen = Counter((c.patient_id, c.dos, c.cpt) for c in claims)
    return {k for k, n in seen.items() if n > 1}


def scrub(claims, today=None):
    today = today or date.today()
    dupes = detect_duplicates(claims)
    results = []
    for c in claims:
        findings = scrub_claim(c, today)
        if (c.patient_id, c.dos, c.cpt) in dupes:
            from scrub_rules import Finding
            findings.append(Finding("DUP", "error",
                                    f"Duplicate line: patient/DOS/CPT repeats in this batch"))
        results.append({"claim": c, "findings": findings})
    return results


def summarize(results):
    errors = warnings = 0
    by_rule = Counter()
    by_payer_err = defaultdict(float)
    flagged = 0
    at_risk = 0.0
    total = len(results)
    for r in results:
        c, findings = r["claim"], r["findings"]
        has_error = False
        for f in findings:
            by_rule[f.rule_id] += 1
            if f.severity == "error":
                errors += 1
                has_error = True
            else:
                warnings += 1
        if findings:
            flagged += 1
        if has_error:
            at_risk += c.billed_amount
            by_payer_err[c.payer] += c.billed_amount
    return {
        "claims_scrubbed": total,
        "clean_claims": total - flagged,
        "clean_rate_pct": round(100 * (total - flagged) / total, 1) if total else None,
        "claims_flagged": flagged,
        "errors": errors,
        "warnings": warnings,
        "billed_at_risk": round(at_risk, 2),
        "findings_by_rule": [{"rule": k, "count": v} for k, v in by_rule.most_common()],
        "error_dollars_by_payer": [
            {"payer": k, "billed_amount": round(v, 2)}
            for k, v in sorted(by_payer_err.items(), key=lambda kv: -kv[1])
        ],
    }


def print_report(summary, results):
    print("=" * 64)
    print("CLEAN CLAIM SCRUBBER - PRE-SUBMISSION REPORT")
    print("=" * 64)
    print(f"Claims scrubbed  : {summary['claims_scrubbed']}")
    print(f"Clean claims     : {summary['clean_claims']} ({summary['clean_rate_pct']}%)")
    print(f"Flagged claims   : {summary['claims_flagged']}")
    print(f"Findings         : {summary['errors']} errors, {summary['warnings']} warnings")
    print(f"Billed $ at risk : ${summary['billed_at_risk']:,.2f}")

    names = {
        "REQ": "Missing required fields", "NPI": "Invalid NPI", "DATE": "Bad dates",
        "TF": "Timely filing", "CODE": "Code format", "MOD": "Modifier issues",
        "NCCI": "Bundling conflicts", "POS": "POS/code mismatch", "UNIT": "Units",
        "CHG": "Charges", "SEX": "Sex-specific conflict", "COB": "Coordination of benefits",
        "DUP": "Duplicates",
    }
    print("\n-- Findings by rule " + "-" * 44)
    for row in summary["findings_by_rule"]:
        print(f"  {row['rule']:<5} {names.get(row['rule'], ''):<32} {row['count']:>3}")
    if summary["error_dollars_by_payer"]:
        print("\n-- Error dollars by payer " + "-" * 37)
        for row in summary["error_dollars_by_payer"]:
            print(f"  {row['payer']:<22} ${row['billed_amount']:>12,.2f}")

    print("\n-- Flagged claims (first 15) " + "-" * 34)
    shown = 0
    for r in results:
        if not r["findings"]:
            continue
        shown += 1
        if shown > 15:
            print(f"  ... and {sum(1 for x in results if x['findings']) - 15} more")
            break
        c = r["claim"]
        worst = "E" if any(f.severity == "error" for f in r["findings"]) else "W"
        print(f"  [{worst}] {c.claim_id:<12} {c.payer:<18} {c.cpt:<6} ${c.billed_amount:>9,.2f}")
        for f in r["findings"][:2]:
            print(f"        {f.rule_id}: {f.message}")


def write_findings_csv(results, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["claim_id", "payer", "cpt", "dos", "billed_amount",
                    "severity", "rule_id", "message"])
        for r in results:
            c = r["claim"]
            for f in r["findings"]:
                w.writerow([c.claim_id, c.payer, c.cpt, c.dos,
                            f"{c.billed_amount:.2f}", f.severity, f.rule_id, f.message])


def results_to_json(results):
    out = []
    for r in results:
        c = r["claim"]
        out.append({
            "claim_id": c.claim_id, "payer": c.payer, "cpt": c.cpt, "dos": c.dos,
            "billed_amount": c.billed_amount,
            "findings": [{"rule_id": f.rule_id, "severity": f.severity, "message": f.message}
                         for f in r["findings"]],
        })
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Pre-submission clean claim scrubber")
    parser.add_argument("csv", help="Claims CSV to scrub")
    parser.add_argument("--json", metavar="OUT.json", help="Export scrub summary + details as JSON")
    parser.add_argument("--findings", metavar="OUT.csv", help="Export the findings worklist CSV")
    args = parser.parse_args(argv)

    try:
        claims = load_claims(args.csv)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    results = scrub(claims)
    summary = summarize(results)
    print_report(summary, results)

    if args.json:
        payload = {"summary": summary, "claims": results_to_json(results)}
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        print(f"\nJSON written to {args.json}")
    if args.findings:
        write_findings_csv(results, args.findings)
        print(f"Findings worklist written to {args.findings}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
