"""Agent base class: one Muse Spark conversation with its own instructions, an allowlisted subset of the
AgentToolbox tools, and a JSON-schema-constrained final answer (Responses API `text.format`).

Agents never touch the database directly. Tool calls go through the shared AgentToolbox (which owns every
security check); timeline rows go through the thread-safe EventLog. An agent without tools (planner,
reviewer, intake) therefore holds no Session at all and is safe to run in a worker thread.
"""

import json
import re
import time
from typing import Any

from openai import APIConnectionError, APITimeoutError

from app.ai.tools import TOOL_SPECS, AgentToolbox, EventLog
from app.config import Settings


class AgentError(RuntimeError):
    """The agent could not produce a usable answer. `code` is safe to store as the run error."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def safe_error(exc: Exception) -> str:
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return "Couldn't reach Muse Spark (network problem). Please try again"
    status = getattr(exc, "status_code", None)
    return f"Muse Spark request failed ({type(exc).__name__}{f' {status}' if status else ''})"


def obj(props: dict, required: list[str] | None = None) -> dict:
    """Strict-subset JSON schema object: closed, every property required."""
    return {"type": "object", "properties": props, "required": required or list(props), "additionalProperties": False}


def nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


STR = {"type": "string"}
STRS = {"type": "array", "items": STR}


def message_texts(resp) -> list[str]:
    out = []
    for item in getattr(resp, "output", None) or []:
        if getattr(item, "type", None) == "message":
            for part in getattr(item, "content", None) or []:
                text = getattr(part, "text", None)
                if getattr(part, "type", None) == "output_text" and text and text.strip():
                    out.append(text.strip())
    return out


def parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("not an object")
    return data


class Agent:
    """Subclasses set `name`, `instructions`, `tools` (allowlist) and `schema`; orchestra agents also
    implement `brief(data, feedback)` (the user turn) and `fallback(data, feedback)` (offline rules)."""

    name: str = "agent"
    instructions: str = ""
    tools: tuple[str, ...] = ()
    schema: dict = {}
    effort: str | None = None  # reasoning effort override; defaults to settings.agent_reasoning_effort

    def __init__(self, settings: Settings, client=None, log: EventLog | None = None, toolbox: AgentToolbox | None = None):
        self.settings, self.client, self.log, self.toolbox = settings, client, log, toolbox
        self._last_id: str | None = None  # conversation to continue when the reviewer sends work back
        self.seconds = 0.0

    @property
    def live(self) -> bool:
        return self.client is not None

    # ----- timeline -----
    def emit(self, kind: str, summary: str, tool_name: str | None = None) -> None:
        if self.log is not None:
            self.log.add(kind, summary, tool_name, agent=self.name)

    def humanize(self, text: str) -> str:
        return self.toolbox.humanize(text) if self.toolbox else text

    # ----- orchestra entry -----
    def run(self, data: dict, feedback: str | None = None) -> dict:
        started = time.monotonic()
        try:
            if not self.live:
                return self.fallback(data, feedback)
            if feedback and self._last_id:
                note = f"Reviewer feedback (revise your answer and reply with the same JSON format): {feedback}"
                return self.converse(note, previous=self._last_id)
            return self.converse(self.brief(data, feedback))
        finally:
            self.seconds += time.monotonic() - started

    def brief(self, data: dict, feedback: str | None) -> str:
        raise NotImplementedError

    def fallback(self, data: dict, feedback: str | None) -> dict:
        raise NotImplementedError

    # ----- Muse Spark loop -----
    def _specs(self) -> list[dict]:
        return [t for t in TOOL_SPECS if t["name"] in self.tools]

    def _call_tool(self, name: str, arguments) -> dict:
        if name not in self.tools:  # allowlist per agent; the toolbox's own checks still apply to allowed tools
            safe = re.sub(r"[^A-Za-z0-9_.-]", "", str(name))[:60] or "unknown"
            self.emit("error", f"Rejected tool '{safe}': not allowed for the {self.name}", safe)
            return {"error": f"tool '{safe}' is not available to you. Your tools: {list(self.tools) or 'none'}"}
        return self.toolbox.execute(name, arguments, agent=self.name)

    def converse(self, prompt: str, previous: str | None = None) -> dict:
        """Run the bounded tool loop and return the schema-shaped final answer."""
        common: dict[str, Any] = {
            "model": self.settings.meta_model,
            "instructions": self.instructions,
            "reasoning": {"effort": self.effort or self.settings.agent_reasoning_effort},
            "text": {"format": {"type": "json_schema", "name": f"{self.name}_answer", "schema": self.schema, "strict": True}},
        }
        if self.tools:
            common["tools"] = self._specs()
        req: dict[str, Any] = {"input": [{"role": "user", "content": prompt}]}
        if previous:
            req["previous_response_id"] = previous
        for _ in range(self.settings.agent_max_tool_rounds + 1):
            resp = self.client.responses.create(**common, **req)
            self._last_id = resp.id
            calls = [i for i in (resp.output or []) if getattr(i, "type", None) == "function_call"]
            texts = message_texts(resp)
            if not calls:
                if not texts:
                    raise AgentError(f"{self.name}_no_answer")
                try:
                    return parse_json(texts[-1])
                except ValueError:
                    raise AgentError(f"{self.name}_bad_answer")
            for text in texts:  # narration between tool calls
                self.emit("model", self.humanize(text))
            outputs = [
                {"type": "function_call_output", "call_id": c.call_id, "output": json.dumps(self._call_tool(c.name, c.arguments), default=str)}
                for c in calls
            ]
            req = {"previous_response_id": resp.id, "input": outputs}
        raise AgentError("tool_round_limit")
