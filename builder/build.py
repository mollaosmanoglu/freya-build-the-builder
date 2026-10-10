"""Entry point for the submission: one brief in, one phone agent out, no manual step.

    python3 builder/build.py {brief_path} {tool_api_path} 2>&1 | tee traces/<name>.log

Same approach as examples/agent_builder.py (Claude Agent SDK + the build-phone-agent skill), but it takes the
tool API file as an argument, because every hidden brief comes with its own. Nothing from any brief is written
into this file: it only passes the two paths on.

Needs FREYA_API_KEY and FREYA_BANK_TEAM_KEY (see env.example) and a Claude login or ANTHROPIC_API_KEY.
"""
import asyncio, dataclasses, json, os, pathlib, sys, time

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, ToolUseBlock, query

KIT = pathlib.Path(__file__).resolve().parent.parent


async def main(brief_path, tool_api_path):
    brief, api = pathlib.Path(brief_path).resolve(), pathlib.Path(tool_api_path).resolve()
    for p in (brief, api):
        if not p.is_file():
            sys.exit(f"not a file: {p}")
    trace = KIT / "traces" / (time.strftime("%Y%m%d-%H%M%S") + ".jsonl")
    trace.parent.mkdir(exist_ok=True)
    options = ClaudeAgentOptions(
        cwd=KIT,
        model=os.environ.get("BUILDER_MODEL", "claude-opus-5-5"),
        skills=["build-phone-agent"],
        setting_sources=["project"],
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
        permission_mode="dontAsk",
        max_turns=150,
        env={"BASH_DEFAULT_TIMEOUT_MS": "900000", "BASH_MAX_TIMEOUT_MS": "1200000", "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"},
    )
    prompt = (f"Use the build-phone-agent skill to build a phone agent for the brief {brief}. "
              f"The bank's tool API for this brief is {api}: read it instead of tools/openapi.json.")
    print(f"start {time.strftime('%Y-%m-%dT%H:%M:%S%z')} brief={brief} tool_api={api} model={options.model}", flush=True)
    with trace.open("w") as out:
        out.write(json.dumps({"start": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "brief": str(brief), "tool_api": str(api), "model": options.model}) + "\n")
        async for message in query(prompt=prompt, options=options):
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


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
