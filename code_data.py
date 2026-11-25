"""Reference code data used by the claim scrubber.

In production scrubbers these tables are compiled from the official CMS
datasets. This module ships a curated, representative subset so the tool
works out of the box with zero setup; run ``cms_fetch.py`` to download the
full quarterly NCCI PTP edit file directly from CMS and extend the
built-in tables automatically.

Sources:
  * NCCI PTP edits: https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits
  * NCCI Policy Manual: https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits
  * LCDs / NCDs (Medicare Coverage Database): https://www.cms.gov/medicare-coverage-database/search.aspx
  * ICD-10-CM code sets: https://www.cms.gov/medicare/coding-billing/icd-10-codes
"""

import os

# Place of Service (CMS POS code set, partial - the most-used entries)
POS_CODES = {
    "02": "Telehealth - other than patient's home",
    "10": "Telehealth - patient's home",
    "11": "Office",
    "12": "Home",
    "19": "Off campus-outpatient hospital",
    "21": "Inpatient hospital",
    "22": "On campus-outpatient hospital",
    "23": "Emergency room - hospital",
    "24": "Ambulatory surgical center",
    "31": "Skilled nursing facility",
    "32": "Nursing facility",
    "81": "Independent laboratory",
}

# Common modifiers (CPT/HCPCS)
MODIFIERS = {
    "25": "Significant, separately identifiable E/M on same day as procedure",
    "26": "Professional component",
    "50": "Bilateral procedure",
    "51": "Multiple procedures",
    "59": "Distinct procedural service",
    "76": "Repeat procedure, same physician",
    "77": "Repeat procedure, another physician",
    "78": "Unplanned return to OR, related procedure",
    "79": "Unrelated procedure during post-op period",
    "90": "Reference (outside) laboratory",
    "91": "Repeat clinical diagnostic laboratory test",
    "95": "Synchronous telemedicine service",
    "TC": "Technical component",
    "XE": "Separate encounter",
    "XS": "Separate structure",
    "XU": "Unusual non-overlapping service",
}

# NCCI PTP edits (comprehensive/column 1 -> component/column 2).
# Curated representative pairs; cms_fetch.py can load the full quarterly
# CMS practitioner file into cms_data/ncci_ptp_pairs.txt.
NCCI_PTP_PAIRS = {
    ("80053", "82040"),   # comprehensive metabolic panel / albumin
    ("80053", "82310"),   # comprehensive metabolic panel / calcium
    ("80053", "82947"),   # comprehensive metabolic panel / glucose
    ("80053", "84132"),   # comprehensive metabolic panel / potassium
    ("80053", "84550"),   # comprehensive metabolic panel / uric acid
    ("80061", "82465"),   # lipid panel / total cholesterol
    ("80061", "83718"),   # lipid panel / HDL
    ("80061", "84478"),   # lipid panel / triglycerides
    ("80076", "82040"),   # hepatic function panel / albumin
    ("80076", "82247"),   # hepatic function panel / bilirubin total
    ("85025", "85027"),   # CBC w/ diff / CBC w/o diff
    ("85025", "85004"),   # CBC w/ diff / automated diff WBC
    ("74177", "74176"),   # CT abd+pelvis w/ contrast / CT abdomen
    ("74178", "74176"),   # CT abd+pelvis w/o contrast / CT abdomen
    ("74178", "74177"),   # CT abd+pelvis without / with contrast
    ("70553", "70551"),   # MRI brain w/ & w/o contrast / w/o contrast
    ("70553", "70552"),   # MRI brain w/ & w/o / with contrast
    ("72148", "72141"),   # MRI lumbar w/o / MRI cervical w/o (spine survey)
    ("73721", "73718"),   # MRI lower extremity joint / non-joint
    ("95810", "95811"),   # polysomnography 4+ params / with CPAP
    ("96374", "96372"),   # IV push infusion / therapeutic injection
    ("99213", "36415"),   # bundled when drawn on same encounter without 25
    ("99214", "93000"),   # E/M / ECG interpretation (illustrative)
    ("93015", "93016"),   # CV stress test / physician supervision only
}

# Modifiers that can legitimately bypass a PTP edit (with documentation)
NCCI_OVERRIDE_MODIFIERS = {"59", "XE", "XS", "XU", "25"}

# Representative Medicare LCD medical-necessity policies.
# cpt -> {"lcd": label, "dx": covered ICD-10-CM prefixes}
# Curated subset in the style of common LCDs; full policies live in the
# Medicare Coverage Database (link at top of file).
LCD_POLICIES = {
    "82306": {  # Vitamin D; 25-hydroxy
        "lcd": "Vitamin D Assay Testing",
        "dx": ("E55", "E20", "E21", "E83.3", "E83.5", "K90", "M80", "M81",
               "N18", "N25", "T79", "Z90.49", "E84"),
    },
    "83036": {  # Hemoglobin A1c
        "lcd": "Glycated Hemoglobin / Glycated Protein",
        "dx": ("E08", "E09", "E10", "E11", "E13", "O24", "R73.0",
               "Z79.84", "Z86.32", "Z83.3"),
    },
    "80061": {  # Lipid panel
        "lcd": "Lipid Testing",
        "dx": ("E78", "I10", "I11", "I20", "I21", "I25", "I63", "I65",
               "I66", "I67", "I69", "I70", "E08", "E09", "E10", "E11",
               "E13", "N04", "N18", "K70", "K74", "K76", "Z79.82",
               "Z79.84", "Z79.89"),
    },
    "84443": {  # TSH
        "lcd": "Thyroid Testing",
        "dx": ("E03", "E04", "E05", "E06", "E07", "E89.0", "R94.6",
               "Z79.899", "E88.9", "D34", "C73"),
    },
    "84153": {  # PSA total
        "lcd": "Prostate Specific Antigen",
        "dx": ("C61", "D07.5", "D29.1", "D40.0", "N40", "N42.9",
               "R97.2", "Z85.46", "Z12.5", "Z80.42"),
    },
}

# ICD-10-CM codes not acceptable as a primary/first-listed diagnosis
# (Medicare Code Edits style: supplementary etiology and factor codes).
ICD_NOT_PRIMARY = {
    "B95.0", "B95.1", "B95.2", "B95.61", "B95.62", "B95.7", "B95.8",
    "B96.0", "B96.1", "B96.20", "B96.29", "B96.81", "B96.89",
    "B97.10", "B97.11", "B97.12", "B97.19", "B97.21", "B97.29",
    "Z68.1", "Z68.20", "Z68.25", "Z68.41", "Z68.45",
}

# Excludes1-style conflicts (prefix pairs that must not be coded together).
# Representative samples from ICD-10-CM Excludes1 notes.
ICD_EXCLUDES1_PAIRS = [
    ("I10", "I11"),    # essential HTN vs hypertensive heart disease
    ("I10", "I12"),    # essential HTN vs hypertensive CKD
    ("I10", "I15"),    # essential HTN vs secondary HTN
    ("E10", "E11"),    # type 1 vs type 2 diabetes
    ("E11", "E13"),    # type 2 vs other specified diabetes
    ("G43", "G44"),    # migraine vs other headache syndromes
]

# ICD-10 categories complete at 3 characters (no 4th digit required),
# so the specificity check should not warn on them. Curated list.
ICD10_COMPLETE_3CHAR = {"I10", "E03", "K21", "J45", "M17", "G47"}

# CPT codes that are inpatient-only per CMS (partial list)
INPATIENT_ONLY_CPTS = {"29881", "27447", "27130"}

# Sex-specific CPT codes -> required patient sex
SEX_SPECIFIC_CPTS = {
    "55700": "M",  # prostate biopsy
    "58150": "F",  # total abdominal hysterectomy
    "58180": "F",
}

# Typical timely-filing limits in days, keyed by lowercased payer keyword
TIMELY_FILING_DAYS = {
    "medicare": 365,
    "cgs": 365,          # CGS Medicare (LCD/MAC contractor for many states)
    "novitas": 365,
    "humana": 365,
    "medicaid": 180,
    "aetna": 180,
    "cigna": 180,
    "united": 180,
    "uhc": 180,
    "bcbs": 365,
    "blue cross": 365,
    "anthem": 365,
    "kaiser": 180,
}
DEFAULT_TIMELY_FILING_DAYS = 180


def timely_filing_limit(payer):
    p = payer.lower()
    for key, days in TIMELY_FILING_DAYS.items():
        if key in p:
            return days
    return DEFAULT_TIMELY_FILING_DAYS


def load_cms_ncci_extra(path=None):
    """Merge additional NCCI PTP pairs downloaded from CMS by cms_fetch.py."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "cms_data", "ncci_ptp_pairs.txt")
    pairs = set()
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    c1, _, c2 = line.partition(",")
                    if c1.strip() and c2.strip():
                        pairs.add((c1.strip(), c2.strip()))
    except OSError:
        pass
    return pairs
