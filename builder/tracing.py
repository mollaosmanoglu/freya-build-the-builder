"""Optional Langfuse tracing for the builder. Does nothing unless LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set,
so the builder runs the same without it (for example when someone else reruns it from a clean clone).

    export LANGFUSE_PUBLIC_KEY=pk-lf-...  LANGFUSE_SECRET_KEY=sk-lf-...  LANGFUSE_BASE_URL=https://us.cloud.langfuse.com

One build = one trace:
    build-phone-agent      (agent)       input: brief + tool API file names, output: Claude's final summary
      decide-next-step     (generation)  one per Claude model call: model, tokens, thinking, text, requested tool calls
      Bash / Read / Edit   (tool)        one per tool call: input and output, ERROR level when the tool failed
Generations are built here from the Agent SDK message stream rather than with the OpenInference instrumentor, because that
one collapses the whole run into a single observation, so you can't see what Claude decided after each tool result.
Secrets are masked before anything leaves the machine.
"""
import json, os, re

_SECRET = re.compile(r"(fak_|sk-ant-|sk-lf-|pk-lf-|sk-)[A-Za-z0-9_\-]{8,}")
_MAX = 20_000                                       # characters kept per tool output


def mask(data, **_):
    """Langfuse calls this on every input/output before it leaves the machine. Replace anything that looks like a key."""
    if isinstance(data, str): return _SECRET.sub(lambda m: m.group(1) + "***", data)
    if isinstance(data, dict): return {k: mask(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)): return [mask(v) for v in data]
    return data


def setup():
    """Return a Langfuse client, or None when tracing is off or langfuse isn't installed."""
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")): return None
    try:
        from langfuse import Langfuse
    except ImportError:
        print("tracing off: pip install langfuse", flush=True); return None
    return Langfuse(mask=mask, environment=os.environ.get("LANGFUSE_TRACING_ENVIRONMENT", "development"),
                    release=os.environ.get("BUILDER_RELEASE"))


def _text(content):
    if isinstance(content, str): return content[:_MAX]
    return json.dumps(content, default=str)[:_MAX]


class Recorder:
    """Turns the Claude Agent SDK message stream into generation and tool observations under the current observation."""

    def __init__(self, lf, prompt):
        self.lf, self.tools, self.gen = lf, {}, None
        self.pending = [{"role": "user", "content": prompt}]        # what the next model call receives

    def message(self, m):
        kind = type(m).__name__
        if kind == "AssistantMessage": self._assistant(m)
        elif kind == "UserMessage" and isinstance(m.content, list): self._tool_results(m)

    def _assistant(self, m):
        if self.gen is None or self.gen["id"] != m.message_id:      # one model call arrives as several messages, one per block
            self._end_generation()
            obs = self.lf.start_observation(as_type="generation", name="decide-next-step", model=m.model, input=self.pending)
            self.gen = {"id": m.message_id, "obs": obs, "text": [], "thinking": [], "calls": [], "usage": None, "stop": None}
            self.pending = []
        g = self.gen
        g["usage"], g["stop"] = m.usage or g["usage"], m.stop_reason or g["stop"]
        for b in m.content:
            kind = type(b).__name__
            if kind == "TextBlock": g["text"].append(b.text)
            elif kind == "ThinkingBlock": g["thinking"].append(b.thinking)
            elif kind == "ToolUseBlock":
                g["calls"].append({"id": b.id, "type": "function", "function": {"name": b.name, "arguments": json.dumps(b.input, default=str)}})
                self.tools[b.id] = self.lf.start_observation(as_type="tool", name=b.name, input=b.input)

    def _tool_results(self, m):
        self._end_generation()
        for b in m.content:
            if type(b).__name__ != "ToolResultBlock": continue
            text = _text(b.content)
            self.pending.append({"role": "tool", "tool_call_id": b.tool_use_id, "content": text})
            obs = self.tools.pop(b.tool_use_id, None)
            if obs:
                obs.update(output=text, **({"level": "ERROR", "status_message": text[:200]} if b.is_error else {}))
                obs.end()

    def _end_generation(self):
        g, self.gen = self.gen, None
        if not g: return
        u = g["usage"] or {}
        usage = {"input": u.get("input_tokens", 0), "output": u.get("output_tokens", 0),
                 "cache_read_input_tokens": u.get("cache_read_input_tokens", 0), "cache_creation_input_tokens": u.get("cache_creation_input_tokens", 0)}
        out = {"role": "assistant", "content": "\n".join(g["text"]) or None}
        if g["calls"]: out["tool_calls"] = g["calls"]
        g["obs"].update(output=out, usage_details=usage, metadata={"stop_reason": g["stop"], "thinking": "\n".join(g["thinking"]) or None})
        g["obs"].end()

    def close(self):
        """Finish anything still open, for example when the run stopped mid tool call."""
        self._end_generation()
        for obs in self.tools.values():
            obs.update(level="WARNING", status_message="no result before the run ended"); obs.end()
        self.tools.clear()
