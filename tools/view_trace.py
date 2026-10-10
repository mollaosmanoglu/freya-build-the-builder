"""Turn a builder trace (traces/*.jsonl from builder/build.py or examples/agent_builder.py) into a local HTML page:
what Claude thought, which files it read, which commands it ran, what came back, and a summary of the run.

    python3 tools/view_trace.py                       # newest trace in traces/
    python3 tools/view_trace.py traces/<file>.jsonl

Writes results/view/trace-<name>.html and opens it. Standard library only.
"""
import html, json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = """body{font:14px/1.45 -apple-system,Segoe UI,sans-serif;margin:0;background:#f6f7f9;color:#1d2330}
header{background:#1d2330;color:#fff;padding:14px 24px}header h1{margin:0;font-size:17px}header .sub{opacity:.75;margin-top:4px}
main{max-width:1000px;margin:18px auto;padding:0 16px}.row{margin:8px 0}.card{border-radius:8px;padding:8px 12px;border:1px solid #dde1e8;background:#fff}
.think{background:#f7f7fa;color:#5a6378;font-style:italic}.say{background:#eefaf1;border-color:#bfe6c9}.tool{background:#f4eefc;border-color:#d5c3ef}
.err{background:#ffeaea;border-color:#f3b3b3}.who{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#6b7488;margin-bottom:3px}
details summary{cursor:pointer;color:#4a5570}pre{margin:6px 0 0;white-space:pre-wrap;word-break:break-word;font:12px/1.4 ui-monospace,Menlo,monospace;background:#f4f5f8;padding:8px;border-radius:6px;max-height:420px;overflow:auto}
.cmd{font:12px ui-monospace,Menlo,monospace}table{border-collapse:collapse;background:#fff;margin:8px 0}td,th{border:1px solid #dde1e8;padding:4px 10px;text-align:left}
h2{font-size:14px;margin:22px 0 4px}"""
LIMIT = 6000

def esc(x): return html.escape(str(x))
def clip(s):
    s = s if isinstance(s, str) else json.dumps(s, indent=1, ensure_ascii=False, default=str)
    return esc(s if len(s) <= LIMIT else s[:LIMIT] + f"\n… ({len(s) - LIMIT} more characters)")

def tool_summary(name, inp):
    if name in ("Read", "Write", "Edit"): return f'{name} {inp.get("file_path", "")}'
    if name == "Bash": return "Bash: " + (inp.get("command", "").strip().splitlines() or [""])[0][:150]
    if name in ("Glob", "Grep"): return f'{name} {inp.get("pattern", "")}'
    return f"{name} {json.dumps(inp, default=str)[:120]}"

def main():
    p = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else max((ROOT / "traces").glob("*.jsonl"), key=lambda f: f.stat().st_mtime)
    lines = [json.loads(l) for l in open(p) if l.strip()]
    start = lines[0] if "start" in lines[0] else {}
    result = next((x for x in lines if x.get("type") == "ResultMessage"), {})
    results, rows, files, cmds, n_tools = {}, [], [], [], 0
    for x in lines:
        if x.get("type") == "UserMessage" and isinstance(x.get("content"), list):
            for b in x["content"]:
                if "tool_use_id" in b: results[b["tool_use_id"]] = b
    for x in lines:
        if x.get("type") != "AssistantMessage": continue
        for b in x["content"]:
            if "thinking" in b: rows.append(f'<div class="row card think"><div class="who">thinking</div>{clip(b["thinking"])}</div>')
            elif "text" in b: rows.append(f'<div class="row card say"><div class="who">claude says</div>{esc(b["text"])}</div>')
            elif "name" in b:
                n_tools += 1; inp, name = b["input"], b["name"]
                if name == "Read": files.append(inp.get("file_path", ""))
                if name == "Bash": cmds.append(inp.get("command", ""))
                r = results.get(b["id"], {}); bad = r.get("is_error")
                out = r.get("content", "")
                if isinstance(out, list): out = "\n".join(c.get("text", "") for c in out if isinstance(c, dict))
                detail = json.dumps(inp, indent=1, ensure_ascii=False) if name != "Bash" else inp.get("command", "")
                rows.append(f'<div class="row card tool {"err" if bad else ""}"><div class="who">tool · {esc(name)}{" · ERROR" if bad else ""}</div>'
                            f'<b class="cmd">{esc(tool_summary(name, inp))}</b>'
                            f'<details><summary>input</summary><pre>{clip(detail)}</pre></details>'
                            f'<details><summary>result</summary><pre>{clip(out)}</pre></details></div>')
    usage = result.get("usage") or {}
    facts = [("model", start.get("model")), ("brief", pathlib.Path(start.get("brief", "")).name), ("started", start.get("start")),
             ("duration", f'{(result.get("duration_ms") or 0) / 1000:.0f} s'), ("turns", result.get("num_turns")), ("tool calls", n_tools),
             ("output tokens", usage.get("output_tokens")), ("cost (list price)", f'${result.get("total_cost_usd") or 0:.2f}'),
             ("result", "error" if result.get("is_error") else result.get("subtype"))]
    tbl = "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in facts)
    fl = "".join(f"<tr><td>{esc(f)}</td></tr>" for f in dict.fromkeys(files))
    summary = (f"<h2>Run</h2><table>{tbl}</table><h2>Files read ({len(set(files))})</h2><table>{fl}</table>"
               f"<h2>Final message</h2><div class='card say'>{esc(result.get('result') or '')}</div><h2>Timeline</h2>")
    out = ROOT / "results" / "view"; out.mkdir(parents=True, exist_ok=True)
    f = out / f"trace-{p.stem}.html"
    f.write_text(f"<!doctype html><meta charset=utf-8><title>trace {esc(p.stem)}</title><style>{CSS}</style>"
                 f"<header><h1>Builder trace · {esc(p.name)}</h1><div class='sub'>{n_tools} tool calls · {len(cmds)} shell commands</div></header>"
                 f"<main>{summary}{''.join(rows)}</main>")
    print(f)
    subprocess.run(["open", str(f)], check=False)

if __name__ == "__main__": main()
