"""Turn one finished call into a local HTML page: nodes entered, what was said, every tool call with its
request and result, each routing decision with the branches it tested, and the variables that changed.

    python3 tools/view_call.py --results results/run.json --case PUB-04     # a case from a run_cases.py --out file
    python3 tools/view_call.py --call <call_id>                              # any call id
    python3 tools/view_call.py --results results/run.json                    # every case, one page each, plus an index

Writes to results/view/ and opens the page. Standard library plus freya.py. Needs FREYA_API_KEY.
"""
import argparse, html, json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import freya

CSS = """body{font:14px/1.45 -apple-system,Segoe UI,sans-serif;margin:0;background:#f6f7f9;color:#1d2330}
header{background:#1d2330;color:#fff;padding:14px 24px}header h1{margin:0;font-size:17px}header .sub{opacity:.75;margin-top:4px}
.ok{color:#5be08a}.bad{color:#ff7b7b}main{max-width:980px;margin:18px auto;padding:0 16px}
.row{display:flex;gap:10px;margin:6px 0}.t{width:52px;flex:none;text-align:right;color:#8a93a6;font-size:12px;padding-top:7px}
.card{flex:1;border-radius:8px;padding:8px 12px;border:1px solid #dde1e8;background:#fff;min-width:0}
.node{background:#e8efff;border-color:#bcd0ff;font-weight:600}.say{background:#eefaf1;border-color:#bfe6c9}
.user{background:#fff7e6;border-color:#f1d9a0}.tool{background:#f4eefc;border-color:#d5c3ef}
.route{background:#fff;border-style:dashed}.err{background:#ffeaea;border-color:#f3b3b3}
.who{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#6b7488;margin-bottom:2px}
details summary{cursor:pointer;color:#4a5570}pre{margin:6px 0 0;white-space:pre-wrap;word-break:break-word;font:12px/1.4 ui-monospace,Menlo,monospace;background:#f4f5f8;padding:8px;border-radius:6px}
.br{font-size:12px;margin:2px 0}.yes{color:#1b8a42}.no{color:#a0a7b8}.chg{font:12px ui-monospace,Menlo,monospace}
table{border-collapse:collapse;background:#fff}td,th{border:1px solid #dde1e8;padding:5px 10px;text-align:left}"""

def esc(x): return html.escape(str(x))
def pretty(x): return esc(json.dumps(x, indent=1, ensure_ascii=False, default=str)) if not isinstance(x, str) else esc(x)

def events(call):
    out = []
    for m in call.get("messages", []):
        t = float(m.get("secondsFromStart") or 0)
        if m["role"] == "system":
            try: e = json.loads(m["message"])
            except Exception: e = {"event": "raw", "message": m["message"]}
            out.append((t, "sys", e, m.get("nodeId")))
        else:
            out.append((t, m["role"], m["message"], m.get("nodeId")))
    return out

def interesting(vt): return {k: v for k, v in vt.items() if not k.endswith(("current_turns", "total_turns"))}

def render_call(call, title):
    ev, rows, prev_vars, pending = events(call), [], {}, {}
    sc = call.get("successCriteriaResult") or {}
    for t, kind, e, node in ev:
        ts = f'<div class="t">{t:.1f}s</div>'
        if kind == "assistant": body = f'<div class="card say"><div class="who">agent · {esc(node)}</div>{esc(e)}</div>'
        elif kind == "user": body = f'<div class="card user"><div class="who">customer</div>{esc(e)}</div>'
        else:
            n = e.get("event")
            if n == "node_enter":
                body = f'<div class="card node">▶ node <b>{esc(e.get("node"))}</b> <span style="font-weight:400;color:#6b7488">from {esc(e.get("from_node") or "start")}</span></div>'
            elif n == "function_call_start":
                pending[e.get("function")] = e.get("args"); continue
            elif n == "function_call_complete":
                fn, args = e.get("function"), pending.pop(e.get("function"), None)
                res = e.get("result") or {}
                bad = isinstance(res, dict) and (res.get("status") not in (None, "success") or (res.get("status_code") or 200) >= 400)
                req = args
                if isinstance(args, dict) and "body" in args and "url" in args: req = {"url": args["url"], "body": args["body"]}
                elif isinstance(args, dict) and "code" in args: req = {"code": "(python snippet, %d chars)" % len(args["code"])}
                body = (f'<div class="card tool {"err" if bad else ""}"><div class="who">tool · {esc(fn)} · {"FAILED" if bad else "ok"}</div>'
                        f'<details open><summary>request</summary><pre>{pretty(req)}</pre></details>'
                        f'<details open><summary>result</summary><pre>{pretty(res)}</pre></details></div>')
            elif n == "route_evaluated":
                vt = interesting(e.get("variable_table") or {})
                chg = {k: v for k, v in vt.items() if prev_vars.get(k) != v}; prev_vars = vt
                br = "".join(f'<div class="br {"yes" if b.get("result") else "no"}">{"✔" if b.get("result") else "✘"} → {esc(b.get("target"))} · {esc(b.get("description"))}</div>' for b in e.get("branches", []))
                chg_html = f'<details><summary>{len(chg)} variable(s) changed</summary><pre class="chg">{pretty(chg)}</pre></details>' if chg else ""
                body = (f'<div class="card route"><div class="who">route · {esc(e.get("from_node"))} → {esc(e.get("target") if e.get("matched") else "stay")}'
                        f' · {esc(e.get("reason"))}</div>{br}{chg_html}</div>')
            elif n == "error": body = f'<div class="card err"><div class="who">error</div><pre>{pretty(e)}</pre></div>'
            elif n == "call_ended": body = f'<div class="card node">■ call ended: {esc(e.get("reason"))}</div>'
            else: body = f'<div class="card"><div class="who">{esc(n)}</div><pre>{pretty(e)}</pre></div>'
        rows.append(f'<div class="row">{ts}{body}</div>')
    verdict = f'<span class="{"ok" if sc.get("success") else "bad"}">{"judge: pass" if sc.get("success") else "judge: fail"}</span>'
    reason = esc(sc.get("reason") or "")
    head = (f'<header><h1>{esc(title)}</h1><div class="sub">{verdict} · ended: {esc(call.get("endedReason"))} · {esc(call.get("duration"))} s'
            f' · call {esc(call.get("id"))}</div><div class="sub">{reason}</div></header>')
    return f"<!doctype html><meta charset=utf-8><title>{esc(title)}</title><style>{CSS}</style>{head}<main>{''.join(rows)}</main>"

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--call"); ap.add_argument("--results"); ap.add_argument("--case"); ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    out = ROOT / "results" / "view"; out.mkdir(parents=True, exist_ok=True)
    jobs = []
    if a.call: jobs.append((a.call, a.call, None))
    elif a.results:
        for r in json.load(open(a.results))["rows"]:
            if (not a.case or r["id"] == a.case) and r.get("call_id"): jobs.append((r["call_id"], r["id"], r))
    else: sys.exit(__doc__)
    if not jobs: sys.exit("no call found")
    made = []
    for cid, name, r in jobs:
        status = "" if r is None else (" PASS" if r["pass"] else " FAIL")
        p = out / f"{name}.html"; p.write_text(render_call(freya.get_call(cid), name + status)); made.append((name, status, p))
    if len(made) > 1:
        idx = out / "index.html"
        li = "".join(f'<tr><td><a href="{p.name}">{esc(n)}</a></td><td class="{"ok" if "PASS" in s else "bad"}">{esc(s.strip())}</td></tr>' for n, s, p in made)
        idx.write_text(f"<!doctype html><meta charset=utf-8><style>{CSS}</style><header><h1>Calls</h1></header><main><table>{li}</table></main>"); target = idx
    else: target = made[0][2]
    print(target)
    if not a.no_open: subprocess.run(["open", str(target)], check=False)

if __name__ == "__main__": main()
