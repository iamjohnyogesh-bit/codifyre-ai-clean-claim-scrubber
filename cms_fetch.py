#!/usr/bin/env python3
"""Fetch official rule data from CMS to extend the built-in scrubber tables.

Currently supported:
  * NCCI PTP practitioner edits - parses the CMS download page, grabs the
    latest quarterly ZIP, extracts the column-1/column-2 pairs and writes
    them to cms_data/ncci_ptp_pairs.txt, which code_data.load_cms_ncci_extra
    merges automatically at runtime.

LCD/NCD policies and ICD-10-CM code sets have licensing/format constraints
that don't fit an automated one-liner; the script prints the official CMS
locations so the curated tables in code_data.py can be maintained against
them.

Usage:
    python3 cms_fetch.py            # fetch + install latest NCCI PTP pairs
    python3 cms_fetch.py --links    # just print the official CMS sources
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import urllib.request
import zipfile

NCCI_PAGE = ("https://www.cms.gov/medicare/coding-billing/"
             "national-correct-coding-initiative-ncci-edits/"
             "medicare-ncci-procedure-procedure-ptp-edits")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cms_data")
OUT_FILE = os.path.join(OUT_DIR, "ncci_ptp_pairs.txt")

LINKS = {
    "NCCI PTP practitioner edits (auto-downloaded by this script)": NCCI_PAGE,
    "NCCI Policy Manual": ("https://www.cms.gov/medicare/coding-billing/"
                           "national-correct-coding-initiative-ncci-edits"),
    "LCD / NCD search (Medicare Coverage Database)":
        "https://www.cms.gov/medicare-coverage-database/search.aspx",
    "ICD-10-CM official code sets": "https://www.cms.gov/medicare/coding-billing/icd-10-codes",
    "Medicare NCCI FAQs": ("https://www.cms.gov/medicare/coding-billing/"
                           "national-correct-coding-initiative-ncci-edits/"
                           "medicare-ncci-faqs"),
}


def _get(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": "codifyre-claim-scrubber/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def find_latest_ptp_zip_url():
    html = _get(NCCI_PAGE).decode("utf-8", "replace")
    hrefs = re.findall(r'href="([^"]+\.zip[^"]*)"', html, re.IGNORECASE)
    # Practitioner PTP edit files (PRA in the filename on CMS)
    pra = [h for h in hrefs if "PRA" in h.upper() or "PRACTITIONER" in h.upper()]
    candidates = pra or hrefs
    if not candidates:
        return None
    url = candidates[0]
    if url.startswith("/"):
        url = "https://www.cms.gov" + url
    return url


def extract_pairs(zip_bytes):
    """Return a set of (column1, column2) 5-char CPT/HCPCS pairs."""
    pairs = set()
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    for name in zf.namelist():
        low = name.lower()
        if not low.endswith(".csv") or "practitioner" not in low and "pra" not in low:
            continue
        with zf.open(name) as fh:
            text = io.TextIOWrapper(fh, encoding="latin-1")
            reader = csv.reader(text)
            header = next(reader, None)
            for row in reader:
                if len(row) < 2:
                    continue
                c1, c2 = row[0].strip(), row[1].strip()
                if re.fullmatch(r"[A-Z0-9]{5}", c1) and re.fullmatch(r"[A-Z0-9]{5}", c2):
                    pairs.add((c1, c2))
        break  # first matching CSV is the practitioner file
    return pairs


def main():
    ap = argparse.ArgumentParser(description="Fetch official CMS scrubber data")
    ap.add_argument("--links", action="store_true",
                    help="print official CMS source URLs and exit")
    args = ap.parse_args()

    if args.links:
        for label, url in LINKS.items():
            print(f"{label}\n  {url}")
        return 0

    print("Reading CMS NCCI PTP edits page ...")
    try:
        zip_url = find_latest_ptp_zip_url()
    except Exception as exc:  # network issues, CMS layout change
        print(f"Could not reach CMS ({exc}). Built-in curated tables remain active.", file=sys.stderr)
        return 1
    if not zip_url:
        print("No PTP ZIP link found on the CMS page (layout may have changed).", file=sys.stderr)
        print("Built-in curated tables remain active.", file=sys.stderr)
        return 1

    print(f"Downloading {zip_url} ...")
    blob = _get(zip_url)
    pairs = extract_pairs(blob)
    if not pairs:
        print("ZIP downloaded but no practitioner PTP CSV found inside.", file=sys.stderr)
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        fh.write("# Official CMS NCCI PTP practitioner edits\n")
        fh.write(f"# Source: {zip_url}\n")
        for c1, c2 in sorted(pairs):
            fh.write(f"{c1},{c2}\n")

    meta = {"source": zip_url, "pairs": len(pairs)}
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)

    print(f"Installed {len(pairs)} official NCCI PTP pairs -> {OUT_FILE}")
    print("The scrubber merges them automatically on its next run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
