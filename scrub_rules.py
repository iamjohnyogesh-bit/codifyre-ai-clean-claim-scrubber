"""Claim scrubbing rules.

Each rule inspects a Claim and yields Finding objects. Rules mirror the
checks production claim scrubbers run before a claim leaves the practice
management system, with rule data sourced from CMS code sets (see
code_data.py for sources and cms_fetch.py to pull the full NCCI PTP file).
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from code_data import (
    ICD10_COMPLETE_3CHAR,
    ICD_EXCLUDES1_PAIRS,
    ICD_NOT_PRIMARY,
    INPATIENT_ONLY_CPTS,
    LCD_POLICIES,
    MODIFIERS,
    NCCI_OVERRIDE_MODIFIERS,
    NCCI_PTP_PAIRS,
    POS_CODES,
    SEX_SPECIFIC_CPTS,
    load_cms_ncci_extra,
    timely_filing_limit,
)

# Built-in curated pairs merged with the full CMS download when present.
NCCI_PTP = set(NCCI_PTP_PAIRS) | load_cms_ncci_extra()

CPT_RE = re.compile(r"^\d{5}$")
HCPCS_RE = re.compile(r"^[A-TV-Z]\d{4}$")
ICD10_RE = re.compile(r"^[A-TV-Z]\d{2}(\.\d{1,4})?$")


@dataclass
class Claim:
    claim_id: str
    patient_id: str
    patient_dob: str          # ISO YYYY-MM-DD
    patient_sex: str          # M / F
    subscriber_id: str
    payer: str
    dos: str                  # ISO YYYY-MM-DD date of service
    pos: str                  # place of service code
    rendering_npi: str
    cpt: str
    modifier: str = ""
    icd10_codes: list = field(default_factory=list)
    units: int = 1
    billed_amount: float = 0.0
    payer_sequence: str = "primary"
    primary_paid_amount: float = None
    same_day_cpts: list = field(default_factory=list)  # other CPTs same DOS, same patient


@dataclass
class Finding:
    rule_id: str
    severity: str             # "error" | "warning"
    message: str


def parse_date(s):
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def npi_valid(npi):
    """Luhn check per the CMS NPI standard (prefix 80840)."""
    digits = [int(c) for c in npi] if npi.isdigit() and len(npi) == 10 else None
    if digits is None:
        return False
    full = [8, 0, 8, 4, 0] + digits
    total = 0
    for i, d in enumerate(reversed(full)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# --- Rules ---------------------------------------------------------------

def rule_required_fields(c):
    req = {
        "subscriber ID": c.subscriber_id,
        "rendering NPI": c.rendering_npi,
        "payer": c.payer,
        "CPT/HCPCS code": c.cpt,
        "place of service": c.pos,
        "date of service": c.dos,
        "patient DOB": c.patient_dob,
    }
    missing = [name for name, val in req.items() if not str(val).strip()]
    if missing:
        yield Finding("REQ", "error", "Missing required field(s): " + ", ".join(missing))
    if not c.icd10_codes:
        yield Finding("REQ", "error", "Missing required field(s): diagnosis code (ICD-10-CM)")


def rule_npi(c):
    if c.rendering_npi and not npi_valid(c.rendering_npi):
        yield Finding("NPI", "error",
                      f"Rendering NPI {c.rendering_npi} fails format/Luhn check")


def rule_dates(c, today):
    try:
        dos = parse_date(c.dos)
    except ValueError:
        yield Finding("DATE", "error", f"Date of service '{c.dos}' is not a valid YYYY-MM-DD date")
        return
    if dos > today:
        yield Finding("DATE", "error", f"Date of service {dos} is in the future")
    try:
        dob = parse_date(c.patient_dob)
        if dob >= dos:
            yield Finding("DATE", "error", f"Patient DOB {dob} is on/after DOS {dos}")
        if (dos - dob).days > 120 * 365:
            yield Finding("DATE", "warning", "Patient age exceeds 120 years - verify DOB")
    except ValueError:
        yield Finding("DATE", "error", f"Patient DOB '{c.patient_dob}' is not a valid YYYY-MM-DD date")


def rule_timely_filing(c, today):
    try:
        dos = parse_date(c.dos)
    except ValueError:
        return
    limit = timely_filing_limit(c.payer)
    age = (today - dos).days
    if age > limit:
        yield Finding("TF", "error",
                      f"Claim is {age} days old; {c.payer} timely filing limit is {limit} days")
    elif age > limit - 30:
        yield Finding("TF", "warning",
                      f"{limit - age} days left before {c.payer} timely filing limit ({limit} days)")


def rule_codes(c):
    if c.cpt and not (CPT_RE.match(c.cpt) or HCPCS_RE.match(c.cpt)):
        yield Finding("CODE", "error", f"'{c.cpt}' is not a valid CPT/HCPCS format")
    if c.pos and c.pos not in POS_CODES:
        yield Finding("CODE", "error", f"Place of service '{c.pos}' is not a recognized CMS POS code")
    if c.modifier:
        for mod in c.modifier.replace(",", " ").split():
            if mod not in MODIFIERS:
                yield Finding("CODE", "warning", f"Modifier '{mod}' is not in the reference list")
    for dx in c.icd10_codes:
        if not ICD10_RE.match(dx):
            yield Finding("CODE", "error", f"Diagnosis '{dx}' is not a valid ICD-10-CM format")
        elif len(dx) < 4 and dx not in ICD10_COMPLETE_3CHAR:
            yield Finding("CODE", "warning",
                          f"Diagnosis '{dx}' has only 3 characters - may require higher specificity")


def rule_pos(c):
    if c.cpt in INPATIENT_ONLY_CPTS and c.pos not in {"21"}:
        yield Finding("POS", "error",
                      f"CPT {c.cpt} is on the CMS inpatient-only list but POS is {c.pos or 'blank'}")


def rule_modifier_logic(c):
    mods = set(c.modifier.replace(",", " ").split())
    if "50" in mods and c.units > 1:
        yield Finding("MOD", "warning",
                      "Bilateral modifier 50 billed with units > 1 - many payers want 1 unit x 150%")
    if "95" in mods and c.pos not in {"02", "10"}:
        yield Finding("MOD", "warning",
                      "Telehealth modifier 95 present but POS is not 02/10 (telehealth)")


def rule_units(c):
    if c.units <= 0:
        yield Finding("UNIT", "error", f"Units must be positive, got {c.units}")
    if c.units > 10:
        yield Finding("UNIT", "warning", f"{c.units} units is unusual - verify before submission")


def rule_charges(c):
    if c.billed_amount <= 0:
        yield Finding("CHG", "error", f"Billed amount must be positive, got {c.billed_amount:.2f}")


def rule_bundling(c):
    for other in c.same_day_cpts:
        if (other, c.cpt) in NCCI_PTP:
            mods = set(c.modifier.replace(",", " ").split())
            if not mods & NCCI_OVERRIDE_MODIFIERS:
                yield Finding("NCCI", "error",
                              f"CPT {c.cpt} is column 2 of an NCCI PTP edit with {other} billed "
                              f"same day - bundles without an override modifier (59/XE/XS/XU)")


def rule_sex_conflict(c):
    want = SEX_SPECIFIC_CPTS.get(c.cpt)
    if want and c.patient_sex != want:
        yield Finding("SEX", "error",
                      f"CPT {c.cpt} is {('male', 'female')[want == 'F']}-specific but patient sex is {c.patient_sex}")


def rule_cob(c):
    if c.payer_sequence.lower() in {"secondary", "tertiary"} and c.primary_paid_amount is None:
        yield Finding("COB", "error",
                      f"{c.payer_sequence.title()} claim missing primary payer paid amount (COB data)")


def rule_lcd(c):
    """Medical-necessity check against built-in LCD dx lists."""
    policy = LCD_POLICIES.get(c.cpt)
    if not policy or not c.icd10_codes:
        return
    covered = any(dx.startswith(prefix)
                  for dx in c.icd10_codes for prefix in policy["dx"])
    if not covered:
        yield Finding("LCD", "error",
                      f"Diagnosis {', '.join(c.icd10_codes)} does not meet medical-necessity "
                      f"criteria of LCD '{policy['lcd']}' for CPT {c.cpt}")


def rule_icd_exclusions(c):
    """ICD-10-CM sequencing: not-primary codes and Excludes1 conflicts."""
    dxs = c.icd10_codes
    if dxs and dxs[0] in ICD_NOT_PRIMARY:
        yield Finding("ICDX", "error",
                      f"Diagnosis {dxs[0]} is not acceptable as the primary/first-listed "
                      f"diagnosis (Medicare code edits) - sequence an etiology code first")
    for p1, p2 in ICD_EXCLUDES1_PAIRS:
        m1 = [d for d in dxs if d.startswith(p1)]
        m2 = [d for d in dxs if d.startswith(p2)]
        if m1 and m2:
            yield Finding("ICDX", "warning",
                          f"ICD-10-CM Excludes1 conflict: {', '.join(m1)} and {', '.join(m2)} "
                          f"should not be coded together")


def scrub_claim(claim, today=None):
    today = today or date.today()
    findings = []
    for rule in (rule_required_fields, rule_npi, rule_dates, rule_timely_filing,
                 rule_codes, rule_pos, rule_modifier_logic, rule_units, rule_charges,
                 rule_bundling, rule_sex_conflict, rule_cob, rule_lcd,
                 rule_icd_exclusions):
        try:
            for f in rule(claim, today) if rule in (rule_dates, rule_timely_filing) else rule(claim):
                findings.append(f)
        except Exception as exc:  # a bad rule must not kill the batch
            findings.append(Finding(rule.__name__, "warning", f"rule failed to run: {exc}"))
    return findings
