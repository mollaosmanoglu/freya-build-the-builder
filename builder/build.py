"""Entry point for the submission: one brief in, one phone agent out, no manual step.

    python3 builder/build.py {brief_path} {tool_api_path} 2>&1 | tee traces/<name>.log

Same approach as examples/agent_builder.py (Claude Agent SDK), but the instructions are a versioned prompt (builder/prompts/) instead of a skill, and it takes the tool API file
as an argument, because every hidden brief comes with its own. Nothing from any brief is written into this file: it only
passes the two paths on.

Needs FREYA_API_KEY and FREYA_BANK_TEAM_KEY (see env.example) and a Claude login or ANTHROPIC_API_KEY.
Optional: set LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL to also send the run to Langfuse (builder/tracing.py).
"""
import asyncio, contextlib, dataclasses, json, os, pathlib, sys, time

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, ToolUseBlock, query

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import tracing

KIT = pathlib.Path(__file__).resolve().parent.parent
PROMPT_VERSION = os.environ.get("BUILDER_PROMPT_VERSION", "v1")      # builder/prompts/<version>.md; change the file's version, never edit a released one


async def main(brief_path, tool_api_path):
    brief, api = pathlib.Path(brief_path).resolve(), pathlib.Path(tool_api_path).resolve()
    for p in (brief, api):
        if not p.is_file():
            sys.exit(f"not a file: {p}")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    # Start every build clean: leftovers from an earlier brief must not leak into this one. Moved, not deleted.
    for old in ("out", "results"):
        if (KIT / old).exists():
            (KIT / "archive" / stamp).mkdir(parents=True, exist_ok=True)
            (KIT / old).rename(KIT / "archive" / stamp / old)
    trace = KIT / "traces" / (stamp + ".jsonl")
    trace.parent.mkdir(exist_ok=True)
    options = ClaudeAgentOptions(
        cwd=KIT,
        model=os.environ.get("BUILDER_MODEL", "claude-opus-5-5"),
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
        permission_mode="dontAsk",
        max_turns=150,
        env={"BASH_DEFAULT_TIMEOUT_MS": "900000", "BASH_MAX_TIMEOUT_MS": "1200000", "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"},
    )
    prompt = (KIT / "builder" / "prompts" / f"{PROMPT_VERSION}.md").read_text().replace("{brief}", str(brief)).replace("{api}", str(api))
    print(f"start {time.strftime('%Y-%m-%dT%H:%M:%S%z')} brief={brief} tool_api={api} model={options.model}", flush=True)

    lf = tracing.setup()
    if lf:
        from langfuse import propagate_attributes
        root = lf.start_as_current_observation(as_type="agent", name="build-phone-agent", input={"brief": brief.name, "tool_api": api.name})
        attrs = propagate_attributes(session_id=f"build-{stamp}", tags=["builder", "claude-agent-sdk", f"prompt-{PROMPT_VERSION}"], version=PROMPT_VERSION,
                                     metadata={"brief": brief.name, "model": options.model, "prompt_version": PROMPT_VERSION, "local_trace": trace.name})
    else:
        root = attrs = contextlib.nullcontext()

    trace_id = None
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
        if rec: rec.close()
    if lf:
        lf.flush()                                  # a short-lived script must flush or the trace never leaves
        print(f"langfuse trace: {lf.get_trace_url(trace_id=trace_id)}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
