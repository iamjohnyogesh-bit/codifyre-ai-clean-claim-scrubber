#!/usr/bin/env python3
"""Render a scrub report JSON as a polished HTML dashboard (dark/light theme).

Usage:
    python claim_scrubber.py data/sample_claims.csv --json scrub_report.json
    python dashboard.py scrub_report.json -o dashboard.html
"""

import argparse
import html
import json
from datetime import date

CSS = """
:root { --bg:#0d1117; --card:#161b22; --border:#30363d; --text:#e6edf3;
        --muted:#8b949e; --accent:#2f81f7; --good:#3fb950; --warn:#d29922; --bad:#f85149;
        --track:#21262d; }
body.light { --bg:#f6f8fa; --card:#ffffff; --border:#d0d7de; --text:#1f2328;
        --muted:#57606a; --accent:#0969da; --good:#1a7f37; --warn:#9a6700; --bad:#cf222e;
        --track:#eaeef2; }
* { box-sizing:border-box; margin:0; padding:0; }
body { background:var(--bg); color:var(--text); font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif; padding:32px; transition:background .2s,color .2s; }
.wrap { max-width:1100px; margin:0 auto; }
header { display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border); padding-bottom:16px; margin-bottom:24px; }
.header-right { display:flex; align-items:center; gap:14px; }
h1 { font-size:24px; } h1 span { color:var(--accent); }
.date { color:var(--muted); font-size:13px; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:14px; margin-bottom:28px; }
.card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:18px; }
.card .label { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.5px; }
.card .value { font-size:28px; font-weight:700; margin-top:6px; }
.card .sub { color:var(--muted); font-size:12px; margin-top:4px; }
.good { color:var(--good); } .bad { color:var(--bad); } .warn { color:var(--warn); }
section { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:20px; margin-bottom:20px; }
h2 { font-size:16px; margin-bottom:16px; }
.bar-row { display:grid; grid-template-columns:190px 1fr 90px; align-items:center; gap:12px; margin-bottom:10px; font-size:13px; }
.bar-row .name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.bar-track { background:var(--track); border-radius:5px; height:20px; overflow:hidden; }
.bar-fill { background:var(--accent); height:100%; border-radius:5px; }
.bar-fill.err { background:var(--bad); }
.bar-row .amt { text-align:right; color:var(--muted); }
table { width:100%; border-collapse:collapse; font-size:13px; }
th { text-align:left; color:var(--muted); font-weight:600; padding:8px 10px; border-bottom:1px solid var(--border); }
td { padding:8px 10px; border-bottom:1px solid var(--track); }
tr:last-child td { border-bottom:none; }
.tag { display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px; }
.tag.e { background:rgba(248,81,73,.15); color:var(--bad); }
.tag.w { background:rgba(210,153,34,.15); color:var(--warn); }
.cols { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
@media (max-width:800px){ .cols { grid-template-columns:1fr; } }
footer { color:var(--muted); font-size:12px; text-align:center; margin-top:24px; }
.theme-btn { background:var(--card); color:var(--text); border:1px solid var(--border); border-radius:8px;
             padding:7px 14px; font-size:13px; cursor:pointer; }
.theme-btn:hover { border-color:var(--accent); }
"""

THEME_SCRIPT = """
(function(){
  var b=document.body, btn=document.getElementById('theme-toggle');
  function apply(t){ b.classList.toggle('light', t==='light');
    btn.textContent = t==='light' ? '\\u263E Dark' : '\\u2600 Light'; }
  var saved=null; try{ saved=localStorage.getItem('codifyre-theme'); }catch(e){}
  apply(saved==='light' ? 'light' : 'dark');
  btn.addEventListener('click', function(){
    var next = b.classList.contains('light') ? 'dark' : 'light';
    apply(next);
    try{ localStorage.setItem('codifyre-theme', next); }catch(e){}
  });
})();
"""

RULE_NAMES = {
    "REQ": "Missing required fields", "NPI": "Invalid NPI", "DATE": "Bad dates",
    "TF": "Timely filing", "CODE": "Code format", "MOD": "Modifier issues",
    "NCCI": "Bundling conflicts", "POS": "POS/code mismatch", "UNIT": "Units",
    "LCD": "LCD necessity", "ICDX": "ICD-10 exclusions",
    "CHG": "Charges", "SEX": "Sex-specific conflict", "COB": "Coordination of benefits",
    "DUP": "Duplicates",
}


def esc(s):
    return html.escape(str(s))


def money(v):
    return f"${v:,.2f}"


def bars(rows, label_key, count_key, money_key=None, err=False):
    if not rows:
        return "<p>No data.</p>"
    peak = max(r[count_key] for r in rows) or 1
    out = []
    for r in rows:
        pct = max(2, round(100 * r[count_key] / peak))
        label = esc(r[label_key])
        amt = money(r[money_key]) if money_key else str(r[count_key])
        cls = "bar-fill err" if err else "bar-fill"
        out.append(
            f'<div class="bar-row"><div class="name">{label}</div>'
            f'<div class="bar-track"><div class="{cls}" style="width:{pct}%"></div></div>'
            f'<div class="amt">{amt}</div></div>'
        )
    return "\n".join(out)


def render(payload, generated=None):
    generated = generated or date.today().isoformat()
    s = payload["summary"]
    claims = payload.get("claims", [])

    cards = [
        ("Claims scrubbed", str(s["claims_scrubbed"]), "", ""),
        ("Clean claim rate", f'{s["clean_rate_pct"]}%',
         f'{s["clean_claims"]} of {s["claims_scrubbed"]} clean', "good"),
        ("Flagged claims", str(s["claims_flagged"]), "", "warn"),
        ("Errors / warnings", f'{s["errors"]} / {s["warnings"]}', "", "bad"),
        ("Billed $ at risk", money(s["billed_at_risk"]), "claims with errors", "bad"),
    ]
    cards_html = "\n".join(
        f'<div class="card"><div class="label">{esc(l)}</div>'
        f'<div class="value {c}">{esc(v)}</div><div class="sub">{esc(sub)}</div></div>'
        for l, v, sub, c in cards
    )

    rule_rows = [{"rule": RULE_NAMES.get(r["rule"], r["rule"]), "count": r["count"]}
                 for r in s.get("findings_by_rule", [])]
    payer_rows = s.get("error_dollars_by_payer", [])

    flagged = [c for c in claims if c["findings"]][:15]
    table_rows = "\n".join(
        f'<tr><td>{esc(c["claim_id"])}</td><td>{esc(c["payer"])}</td>'
        f'<td>{esc(c["cpt"])}</td><td>{money(c["billed_amount"])}</td>'
        f'<td><span class="tag {"e" if any(f["severity"]=="error" for f in c["findings"]) else "w"}">'
        f'{"error" if any(f["severity"]=="error" for f in c["findings"]) else "warning"}</span></td>'
        f'<td>{esc(c["findings"][0]["message"])}</td></tr>'
        for c in flagged
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Codifyre AI - Clean Claim Scrubber Dashboard</title>
<style>{CSS}</style></head><body><div class="wrap">
<header><h1><span>Codifyre AI</span> &middot; Clean Claim Scrubber</h1>
<div class="header-right"><div class="date">Generated {esc(generated)}</div>
<button id="theme-toggle" class="theme-btn">&#9728; Light</button></div></header>
<div class="cards">{cards_html}</div>
<div class="cols">
<section><h2>Findings by rule</h2>{bars(rule_rows, "rule", "count")}</section>
<section><h2>Error dollars by payer</h2>{bars(payer_rows, "payer", "billed_amount", money_key="billed_amount", err=True)}</section>
</div>
<section><h2>Flagged claims</h2>
<table><tr><th>Claim</th><th>Payer</th><th>CPT</th><th>Billed</th><th>Severity</th><th>First finding</th></tr>
{table_rows}</table></section>
<footer>Built by Codifyre AI &middot; github.com/iamjohnyogesh-bit/codifyre-ai-clean-claim-scrubber</footer>
</div><script>{THEME_SCRIPT}</script></body></html>"""


def main():
    parser = argparse.ArgumentParser(description="Render scrub report JSON as an HTML dashboard")
    parser.add_argument("json_path", help="JSON from claim_scrubber.py --json")
    parser.add_argument("-o", "--out", default="dashboard.html")
    args = parser.parse_args()
    with open(args.json_path, encoding="utf-8") as fh:
        payload = json.load(fh)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(render(payload))
    print(f"dashboard written to {args.out}")


if __name__ == "__main__":
    main()
