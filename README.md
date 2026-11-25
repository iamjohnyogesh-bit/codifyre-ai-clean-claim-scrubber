# Codifyre AI - Clean Claim Scrubber

> Pre-submission claim scrubbing for US healthcare revenue cycle teams. Catch the denials before they happen.

**Codifyre AI** builds practical, open-source RCM tooling. This project is Day 2 of the daily build series: Day 1 was [denial-management analytics](https://github.com/iamjohnyogesh-bit/codifyre-ai-denial-management-analytics) (after the denial); Day 2 is prevention (before the claim leaves the door).

## What it does

`claim_scrubber.py` reads a CSV of 837P-style professional claims and runs **15 pre-submission checks** against every line - the same classes of edits a commercial scrubber or clearinghouse applies - then reports:

- a console report (clean rate, findings by rule, error dollars by payer)
- a machine-readable JSON summary
- a line-level findings CSV you can hand back to billers
- an interactive HTML dashboard (dark theme default with a light/dark toggle, persisted per visitor)

Zero dependencies: pure Python 3.9+ standard library.

## Scrubber rules

| Rule | Severity | What it catches |
| --- | --- | --- |
| `REQ` | error | Missing required fields (subscriber ID, NPI, payer, CPT, POS, DOS, DOB, diagnosis) |
| `NPI` | error | Rendering NPI fails the CMS Luhn check |
| `DATE` | error/warning | Invalid dates, future DOS, DOB on/after DOS, implausible age |
| `TF` | error/warning | Payer-specific timely-filing limits (Medicare 365, most commercial 180) with a 30-day early warning |
| `CODE` | error/warning | Malformed CPT/HCPCS, unknown POS, unknown modifiers, low-specificity ICD-10-CM |
| `POS` | error | CMS inpatient-only procedures billed in a non-inpatient setting |
| `MOD` | warning | Modifier logic: bilateral 50 with units > 1, telehealth 95 without POS 02/10 |
| `UNIT` | error/warning | Zero/negative or unusually high units |
| `CHG` | error | Non-positive billed amounts |
| `NCCI` | error | NCCI PTP bundling conflicts billed same day without an override modifier (59/XE/XS/XU) |
| `LCD` | error | Diagnosis does not meet medical-necessity criteria of the built-in LCD policies |
| `ICDX` | error/warning | ICD-10-CM codes not acceptable as primary diagnosis; Excludes1 conflicts |
| `SEX` | error | Sex-specific procedure/patient mismatch |
| `COB` | error | Secondary/tertiary claims missing primary-payer COB amounts |
| `DUP` | error | Exact duplicate claims (same patient, DOS, CPT) |

Duplicates are detected across the batch; everything else runs per claim.

## CMS data sources

The built-in rule tables in `code_data.py` are curated, representative subsets compiled from official CMS sources:

- **NCCI PTP edits** - [CMS Medicare NCCI PTP page](https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-procedure-procedure-ptp-edits)
- **LCD / NCD policies** - [Medicare Coverage Database](https://www.cms.gov/medicare-coverage-database/search.aspx)
- **ICD-10-CM code sets** - [CMS ICD-10 codes](https://www.cms.gov/medicare/coding-billing/icd-10-codes)

### Pull the full NCCI PTP file from CMS

```bash
python3 cms_fetch.py            # downloads the latest quarterly practitioner PTP edits
python3 cms_fetch.py --links    # prints every official CMS source used
```

The fetcher parses the CMS download page, grabs the newest quarterly ZIP, extracts the column-1/column-2 pairs, and writes `cms_data/ncci_ptp_pairs.txt`. The scrubber merges that file automatically on its next run - no code changes. If CMS is unreachable or changes its page layout, the built-in curated tables keep the tool fully functional.

## Quickstart

```bash
# 1. Generate the synthetic demo dataset (85 claims with labeled flaws)
python3 gen_sample_claims.py

# 2. Scrub it
python3 claim_scrubber.py data/sample_claims.csv \
    --json out/summary.json --findings out/findings.csv

# 3. Build the dashboard
python3 dashboard.py out/summary.json -o dashboard.html
# open dashboard.html in any browser - dark theme by default,
# sun/moon button in the header flips to light and remembers your choice

# 4. Run the test suite (16 tests)
python3 -m unittest discover -s tests -v
```

## Sample output

```
================================================================
CLEAN CLAIM SCRUBBER - PRE-SUBMISSION REPORT
================================================================
Claims scrubbed  : 85
Clean claims     : 56 (65.9%)
Flagged claims   : 29
Findings         : 23 errors, 7 warnings
Billed $ at risk : $6,095.00

-- Findings by rule --------------------------------------------
  CODE  Code format                        4
  DUP   Duplicates                         3
  DATE  Bad dates                          3
  ...
```

## Input format

One claim per CSV row. Required columns: `claim_id, patient_id, patient_dob, patient_sex, subscriber_id, payer, dos, pos, rendering_npi, cpt, icd10_codes, units, billed_amount`. Optional: `modifier, payer_sequence, primary_paid_amount`. Separate multiple ICD-10-CM codes with semicolons; the first is treated as primary.

## Project layout

```
claim_scrubber.py     CLI: load, scrub, summarize, console report, JSON/CSV export
scrub_rules.py        the 15 rules + Claim/Finding models + NPI Luhn check
code_data.py          curated CMS rule tables (POS, modifiers, NCCI, LCD, ICD, timely filing)
cms_fetch.py          downloads the official quarterly NCCI PTP file from CMS
dashboard.py          renders the dark/light HTML dashboard from the JSON summary
gen_sample_claims.py  deterministic synthetic claims generator (labeled flaws)
tests/                16 unit tests covering every rule, the batch math and the dashboard
data/sample_claims.csv
```

## License

MIT - see [LICENSE](LICENSE). Built with care by **Codifyre AI**.
