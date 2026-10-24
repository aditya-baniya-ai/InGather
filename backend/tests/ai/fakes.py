"""Scripted stand-in for the Muse Spark Responses API (same shapes as the OpenAI SDK objects we read)."""

import json
from types import SimpleNamespace


def call(name: str, args: dict | str, call_id: str | None = None):
    raw = args if isinstance(args, str) else json.dumps(args)
    return SimpleNamespace(type="function_call", name=name, arguments=raw, call_id=call_id or f"call_{name}", status="completed")


def say(text: str):
    return SimpleNamespace(type="message", role="assistant", content=[SimpleNamespace(type="output_text", text=text)])


def reasoning():
    return SimpleNamespace(type="reasoning", summary=[], encrypted_content=None)


class FakeResponses:
    """`script` is a list of callables `(outputs_by_call_id) -> list[items]`, one per model turn."""

    def __init__(self, script, raise_exc: Exception | None = None):
        self.script, self.raise_exc, self.requests = list(script), raise_exc, []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if self.raise_exc:
            raise self.raise_exc
        outputs = {
            i["call_id"]: json.loads(i["output"])
            for i in kwargs.get("input", [])
            if isinstance(i, dict) and i.get("type") == "function_call_output"
        }
        step = self.script.pop(0) if self.script else (lambda _o: [say("Done.")])
        items = step(outputs)
        return SimpleNamespace(id=f"resp_{len(self.requests)}", output=[reasoning(), *items], model="fake-muse")


class FakeClient:
    def __init__(self, script=(), raise_exc=None):
        self.responses = FakeResponses(script, raise_exc)
