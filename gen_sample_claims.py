#!/usr/bin/env python3
"""Generate a realistic synthetic claims file with intentional, labeled flaws.

The flaws are designed so the scrubber catches every rule at least once:
missing fields, bad NPIs, timely-filing violations, NCCI PTP bundling
conflicts, LCD medical-necessity misses, ICD-10-CM Excludes1 conflicts,
non-primary diagnosis sequencing, duplicates, and more.
"""

import csv
import random
from datetime import date, timedelta

CPT_POOL = ["99213", "99214", "99203", "99204", "93000", "71046", "80053",
            "85025", "36415", "99285", "20610", "97140", "99396", "81001",
            "80061", "83036", "84443", "84153", "82306"]
ICD10S = ["I10", "E11.9", "M54.5", "R07.9", "I25.10", "Z00.00", "R10.9",
          "J02.9", "R05.9", "K21.9"]
PAYERS = ["Aetna", "Cigna", "UnitedHealthcare", "BCBS", "Medicare",
          "CGS Medicare", "Humana", "Medicaid"]

# For CPTs with an LCD policy, clean rows should carry a covered diagnosis
# so the only LCD findings are the intentional flaw rows.
LCD_COVERED_DX = {
    "82306": ["E55.9", "M81.0"],
    "83036": ["E11.9", "R73.01"],
    "80061": ["E78.5", "I10"],
    "84443": ["E03.9", "E05.90"],
    "84153": ["N40.0", "Z12.5"],
}


def luhn_npi(rng):
    """Return a valid 10-digit NPI (starts with 1, valid Luhn check digit)."""
    n = str(rng.randint(10**8, 10**9 - 1))
    n = "1" + n[1:]
    base = "80840" + n  # 14 digits; check digit becomes the 15th
    total = 0
    for i, c in enumerate(reversed(base)):
        d = int(c)
        if (i + 1) % 2 == 1:  # odd positions from the right of the base
            d *= 2
            if d > 9:
                d -= 9
        total += d
    check = (10 - total % 10) % 10
    return n + str(check)


def make_row(i, rng, today, subscriber=None, npi=None, dos=None, dob=None,
             sex=None, payer=None, pos="11", cpt=None, mod="", icd=None,
             units=1, billed=None, seq="primary", primary_paid=None):
    cpt = cpt or rng.choice(CPT_POOL)
    if icd is None:
        icd = rng.choice(LCD_COVERED_DX.get(cpt, ICD10S))
    dos = dos or (today - timedelta(days=rng.randint(3, 120))).isoformat()
    return {
        "claim_id": f"CLM{26000+i}",
        "patient_id": f"PT{rng.randint(1000, 9999)}",
        "patient_dob": dob or (today - timedelta(days=rng.randint(20*365, 70*365))).isoformat(),
        "patient_sex": sex if sex is not None else rng.choice(["M", "F"]),
        "subscriber_id": subscriber if subscriber is not None else f"SUB{rng.randint(10**8, 10**9-1)}",
        "payer": payer or rng.choice(PAYERS),
        "payer_sequence": seq,
        "primary_paid_amount": primary_paid if primary_paid is not None else "",
        "dos": dos,
        "pos": pos,
        "rendering_npi": npi if npi is not None else luhn_npi(rng),
        "cpt": cpt,
        "modifier": mod,
        "icd10_codes": icd,
        "units": units,
        "billed_amount": billed if billed is not None else rng.choice([75, 120, 150, 220, 340, 480, 900]),
    }


def generate(n=85):
    rng = random.Random(20261125)
    today = date.today()
    out = []
    i = 1
    n_flaws = 27
    while len(out) < n - n_flaws - 2:
        out.append(make_row(i, rng, today))
        i += 1

    # Intentional flaws, one row each unless noted
    flaws = [
        lambda: make_row(len(out) + 1, rng, today, subscriber=""),
        lambda: make_row(len(out) + 1, rng, today, icd=""),
        lambda: make_row(len(out) + 1, rng, today, npi="1234567890"),
        lambda: make_row(len(out) + 1, rng, today, npi="12345"),
        lambda: make_row(len(out) + 1, rng, today,
                         dos=(today + timedelta(days=4)).isoformat()),
        lambda: make_row(len(out) + 1, rng, today, dob="1980-05-10",
                         dos="1979-01-01"),
        lambda: make_row(len(out) + 1, rng, today, payer="Aetna",
                         dos=(today - timedelta(days=240)).isoformat()),
        lambda: make_row(len(out) + 1, rng, today, payer="Cigna",
                         dos=(today - timedelta(days=160)).isoformat()),
        lambda: make_row(len(out) + 1, rng, today, pos="99"),
        lambda: make_row(len(out) + 1, rng, today, cpt="99X13"),
        lambda: make_row(len(out) + 1, rng, today, icd="M54"),
        lambda: make_row(len(out) + 1, rng, today, icd="123"),
        lambda: make_row(len(out) + 1, rng, today, cpt="29881", pos="11",
                         icd="M17.9"),
        lambda: make_row(len(out) + 1, rng, today, mod="50", units=2),
        lambda: make_row(len(out) + 1, rng, today, mod="95", pos="11"),
        lambda: make_row(len(out) + 1, rng, today, units=0),
        lambda: make_row(len(out) + 1, rng, today, units=25),
        lambda: make_row(len(out) + 1, rng, today, billed=0),
        lambda: make_row(len(out) + 1, rng, today, cpt="55700", sex="F",
                         icd="R97.2"),
        lambda: make_row(len(out) + 1, rng, today, seq="secondary", payer="Medicare"),
        lambda: make_row(len(out) + 1, rng, today, cpt="82306", icd="J02.9"),   # LCD miss (vitamin D, non-covered dx)
        lambda: make_row(len(out) + 1, rng, today, icd="B96.20"),               # not-primary dx first-listed
        lambda: make_row(len(out) + 1, rng, today, icd="I10;I11.0"),            # Excludes1 conflict
        lambda: make_row(len(out) + 1, rng, today, cpt="83036", icd="R05.9"),   # LCD miss (A1c, non-covered dx)
        lambda: make_row(len(out) + 1, rng, today, dob="1895-03-01"),
    ]
    for f in flaws:
        out.append(f())

    # NCCI PTP conflict: component (82040) + comprehensive (80053) billed
    # same patient, same day, no override modifier.
    ncci_dos = (today - timedelta(days=12)).isoformat()
    for cpt in ("82040", "80053"):
        row = make_row(len(out) + 1, rng, today, cpt=cpt, icd="R79.89",
                       dos=ncci_dos)
        row["patient_id"] = "PT777001"
        out.append(row)

    # Duplicate: exact copy of one clean row
    dup = dict(out[3])
    dup2 = dict(dup)
    out.append(dup)
    out.append(dup2)
    assert len(out) == n, f"generator produced {len(out)} rows, expected {n}"
    return out


def main():
    rows = generate()
    with open("data/sample_claims.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} claims to data/sample_claims.csv")


if __name__ == "__main__":
    main()
