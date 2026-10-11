"""Checks the mock returns exactly the status and body of every entry in test-customers.json.
Usage: python3 mock/check.py [base_url]   (default http://localhost:8787)"""
import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8787").rstrip("/")
DATA = json.loads((Path(__file__).parent / "test-customers.json").read_text())
EMAIL = {"intAddressInfoType": "E"}
PDF = {"cardNumber": "x", "currencyType": "TL", "statementDate": "05.10.2026", "emailAddress": "a@b.example"}


def post(service, data):
    req = urllib.request.Request(f"{BASE}/voice/v1/{service}", json.dumps({"data": data, "call": {"lang": "tr"}}).encode(),
                                 {"content-type": "application/json", "user-agent": "check"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(text)
        except ValueError:
            return e.code, {"raw": text[:200]}


cases = []
for c in DATA["customers"]:
    no, s = c["customerNo"], c["services"]
    for svc, extra in [("cards.list", {}), ("contact.email.get", EMAIL), ("statement.pdf.send", PDF)]:
        if svc in s:
            cases.append((svc, {"customerNo": int(no), **extra}, s[svc]))
    for svc in ["cards.balance", "statement.week.get"]:
        for card, e in s.get(svc, {}).items():
            cases.append((svc, {"cardNumber": card}, e))
    for svc in ["statement.week.decide", "statement.week.change"]:
        for card, weeks in s.get(svc, {}).items():
            for week, e in weeks.items():
                cases.append((svc, {"cardNumber": card, "newStatementWeek": int(week), "statementDay": 5}, e))

with ThreadPoolExecutor(8) as pool:
    results = list(pool.map(lambda c: post(c[0], c[1]), cases))
bad = [(c[0], c[1], r[0], r[1].get("raw", "")) for c, r in zip(cases, results) if r != (c[2]["http"], c[2]["response"])]
print(f"{len(cases) - len(bad)}/{len(cases)} entries match")
for b in bad:
    print("MISMATCH", b)

for svc, data, want in [("cards.list", {"customerNo": "11111111"}, 404), ("cards.balance", {"cardNumber": "999999******0000"}, 404),
                        ("statement.week.get", {"cardNumber": ""}, 400), ("contact.email.get", {"customerNo": "11111111", **EMAIL}, 400),
                        ("statement.pdf.send", {"customerNo": "94907600", **PDF}, 404), ("cards.list", {"customerNo": "{{customerNumber}}"}, 200)]:
    got = post(svc, data)
    print("ok " if got[0] == want else "BAD", svc, data, got[0], got[1].get("result", {}).get("code"))
