"""Scripted stand-in for the Muse Spark Responses API (same shapes as the OpenAI SDK objects we read)."""

import json
from types import SimpleNamespace


def say(text: str):
    return SimpleNamespace(type="message", role="assistant", content=[SimpleNamespace(type="output_text", text=text)])


def answer(data: dict):
    """A structured-output final answer (JSON text in an output_text part)."""
    return say(json.dumps(data))


class FakeResponses:
    """Each `create` call returns the next scripted list of output items and records the request."""

    def __init__(self, script):
        self.script, self.requests = list(script), []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if not self.script:
            raise AssertionError("no scripted turn left")
        reasoning = SimpleNamespace(type="reasoning", summary=[], encrypted_content=None)
        return SimpleNamespace(id=f"resp_{len(self.requests)}", output=[reasoning, *self.script.pop(0)], model="fake-muse")


class FakeMuse:
    def __init__(self, *turns):
        self.responses = FakeResponses(turns)
