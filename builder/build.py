"""Entry point for the submission: one brief in, one phone agent out, no manual step.

    python3 builder/build.py {brief_path} {tool_api_path} 2>&1 | tee traces/<name>.log

Same approach as examples/agent_builder.py (Claude Agent SDK), but the instructions are a versioned prompt (builder/prompts/) instead of a skill, and it takes the tool API file
as an argument, because every hidden brief comes with its own. Nothing from any brief is written into this file: it only
passes the two paths on.

Needs FREYA_API_KEY and FREYA_BANK_TEAM_KEY (see env.example) and a Claude login or ANTHROPIC_API_KEY.
Optional: set LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL to also send the run to Langfuse (builder/tracing.py).
"""
import asyncio, atexit, contextlib, dataclasses, json, os, pathlib, shutil, signal, sys, tempfile, time

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, ToolUseBlock, query

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import tracing

KIT = pathlib.Path(__file__).resolve().parent.parent
# The only files of the kit the agent gets to see. It works in a throwaway copy, so hackathon docs, other briefs, examples and
# earlier results are simply not there.
SANDBOX_FILES = ["docs/workflow-format.md", "docs/tools-and-code.md", "docs/api.md", "freya.py",
                 "tools/run_cases.py", "tools/score.py", "public-test-set.json"]
STATE_FILES = [".freya-agents.json", ".personas.json"]       # ids of the workflows and test customers, copied in and back out
TIME_LIMIT_MIN = float(os.environ.get("BUILDER_TIME_LIMIT_MIN", "28"))   # Freya stops a builder at 30 minutes
PROMPT_VERSION = os.environ.get("BUILDER_PROMPT_VERSION", "v0")      # builder/prompts/<version>.md; change the file's version, never edit a released one


async def main(brief_path, tool_api_path):
    brief, api = pathlib.Path(brief_path).resolve(), pathlib.Path(tool_api_path).resolve()
    for p in (brief, api):
        if not p.is_file():
            sys.exit(f"not a file: {p}")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    box = pathlib.Path(tempfile.mkdtemp(prefix="freya-build-"))
    for f in SANDBOX_FILES + STATE_FILES:
        if (KIT / f).exists():
            (box / f).parent.mkdir(parents=True, exist_ok=True); shutil.copy(KIT / f, box / f)
    agents = box / ".freya-agents.json"
    if agents.exists():               # every build starts from the base workflow only, never from an earlier build's agent
        agents.write_text(json.dumps({k: v for k, v in json.loads(agents.read_text()).items() if k == "base"}, indent=1))
    (box / "brief").mkdir()
    def cleanup():                    # runs however the build ends: keep the ids, throw the rest away
        if agents.exists():
            kept = json.loads((KIT / agents.name).read_text()) if (KIT / agents.name).exists() else {}
            (KIT / agents.name).write_text(json.dumps(kept | json.loads(agents.read_text()), indent=1))
        for f in STATE_FILES:
            if f != agents.name and (box / f).exists(): shutil.copy(box / f, KIT / f)
        shutil.rmtree(box, ignore_errors=True)
    atexit.register(cleanup)
    brief_in, api_in = brief, api
    brief, api = box / "brief" / brief_in.name, box / "brief" / api_in.name
    shutil.copy(brief_in, brief); shutil.copy(api_in, api)
    trace = KIT / "traces" / (stamp + ".jsonl")
    trace.parent.mkdir(exist_ok=True)
    options = ClaudeAgentOptions(
        cwd=box,
        model=os.environ.get("BUILDER_MODEL", "claude-fable-5-1"),
        effort=os.environ.get("BUILDER_EFFORT", "high"),           # low, medium, high or max
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
        permission_mode="dontAsk",
        max_turns=150,
        setting_sources=[],
        env={"BASH_DEFAULT_TIMEOUT_MS": "900000", "BASH_MAX_TIMEOUT_MS": "1200000", "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1", "PWD": str(box), "FREYA_SIM_CONCURRENCY": "30"}   # run all practice customers at once (kit default is 5),
    )
    prompt = (KIT / "builder" / "prompts" / f"{PROMPT_VERSION}.md").read_text().replace("{brief}", str(brief)).replace("{api}", str(api))
    print(f"start {time.strftime('%Y-%m-%dT%H:%M:%S%z')} brief={brief_in} tool_api={api_in} model={options.model} effort={options.effort} sandbox={box}", flush=True)

    lf = tracing.setup()
    if lf:
        from langfuse import propagate_attributes
        root = lf.start_as_current_observation(as_type="agent", name="build-phone-agent", input={"brief": brief.name, "tool_api": api.name})
        attrs = propagate_attributes(session_id=f"build-{stamp}", user_id=os.environ.get("BUILDER_OWNER"), tags=["builder", "claude-agent-sdk", f"prompt-{PROMPT_VERSION}"], version=PROMPT_VERSION,
                                     metadata={"brief": brief.name, "model": options.model, "prompt_version": PROMPT_VERSION, "local_trace": trace.name})
    else:
        root = attrs = contextlib.nullcontext()

    trace_id = None
    rec = None
    try:
        async with asyncio.timeout(TIME_LIMIT_MIN * 60):
            with root as span, attrs, trace.open("w") as out:
                trace_id, rec = (lf.get_current_trace_id(), tracing.Recorder(lf, prompt)) if lf else (None, None)
                out.write(json.dumps({"start": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "brief": str(brief), "tool_api": str(api), "model": options.model, "prompt_version": PROMPT_VERSION}) + "\n")
                async for message in query(prompt=prompt, options=options):
                    if rec: rec.message(message)
                    out.write(json.dumps({"type": type(message).__name__, **dataclasses.asdict(message)}, default=str) + "\n")
                    out.flush()
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                print(block.text, flush=True)
                            elif isinstance(block, ToolUseBlock):
                                print(f"  [{block.name}] {str(block.input)[:120]}", flush=True)
                    elif isinstance(message, ResultMessage):
                        print(f"\nend {time.strftime('%Y-%m-%dT%H:%M:%S%z')}: {message.num_turns} turns, {message.duration_ms / 1000:.0f} s. Trace: {trace}", flush=True)
                        if span is not None:
                            span.update(output=message.result, metadata={"turns": message.num_turns, "cost_usd": message.total_cost_usd},
                                        **({"level": "ERROR", "status_message": message.subtype} if message.is_error else {}))
    except TimeoutError:
        print(f"\nstopped at the {TIME_LIMIT_MIN:g}-minute limit; the last deployed workflow is the result", flush=True)
    finally:                                        # also on Ctrl-C or a kill, so a stopped build keeps its trace
        if rec: rec.close()
        if lf:
            lf.flush()                              # a short-lived script must flush or the trace never leaves
            print(f"langfuse trace: {lf.get_trace_url(trace_id=trace_id)}", flush=True)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
