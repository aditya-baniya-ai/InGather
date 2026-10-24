"""Scripted stand-ins for the Muse Spark Responses API (same shapes as the OpenAI SDK objects we read)."""

import json
import re
import threading
from collections import defaultdict
from types import SimpleNamespace


def call(name: str, args: dict | str, call_id: str | None = None):
    raw = args if isinstance(args, str) else json.dumps(args)
    return SimpleNamespace(type="function_call", name=name, arguments=raw, call_id=call_id or f"call_{name}", status="completed")


def say(text: str):
    return SimpleNamespace(type="message", role="assistant", content=[SimpleNamespace(type="output_text", text=text)])


def reasoning():
    return SimpleNamespace(type="reasoning", summary=[], encrypted_content=None)


def answer(data: dict):
    """A structured-output final answer (JSON text in an output_text part)."""
    return say(json.dumps(data))


class OrchestraResponses:
    """Routes each Responses call to the script of the agent whose instructions it carries. Thread-safe, because
    the scheduler and planner call it concurrently. Each script step is `(outputs_by_call_id, request) -> items`."""

    def __init__(self, raise_exc: Exception | None = None, **scripts):
        self.scripts = {k: list(v) for k, v in scripts.items()}
        self.raise_exc, self.requests, self.threads = raise_exc, defaultdict(list), defaultdict(set)
        self._lock = threading.Lock()

    def create(self, **kwargs):
        m = re.search(r"ROLE: (\w+)\.", kwargs.get("instructions", ""))
        agent = m.group(1).lower() if m else "intake"
        with self._lock:
            self.requests[agent].append(kwargs)
            self.threads[agent].add(threading.get_ident())
            n = len(self.requests[agent])
            step = self.scripts.get(agent, []).pop(0) if self.scripts.get(agent) else None
        if self.raise_exc:
            raise self.raise_exc
        if step is None:
            raise AssertionError(f"no scripted turn left for {agent}")
        outputs = {
            i["call_id"]: json.loads(i["output"])
            for i in kwargs.get("input", [])
            if isinstance(i, dict) and i.get("type") == "function_call_output"
        }
        return SimpleNamespace(id=f"resp_{agent}_{n}", output=[reasoning(), *step(outputs, kwargs)], model="fake-muse")


class OrchestraClient:
    def __init__(self, raise_exc=None, **scripts):
        self.responses = OrchestraResponses(raise_exc, **scripts)
