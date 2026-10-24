"""Live smoke test for the Meta Model API. Prints only success/failure and the model id; never the key.

Run from the repo root or backend/:  cd backend && uv run python ../scripts/smoke_test_meta.py
"""

import json
import os
import sys
from pathlib import Path

from openai import OpenAI


def load_env() -> None:
    for path in (Path.cwd() / ".env", Path.cwd().parent / ".env", Path(__file__).resolve().parents[1] / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and not key.startswith("#") and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")


def main() -> int:
    load_env()
    if not os.environ.get("MODEL_API_KEY"):
        print("FAIL: MODEL_API_KEY is not set")
        return 1
    model = os.environ.get("META_MODEL", "muse-spark-1.3")
    client = OpenAI(
        base_url=os.environ.get("META_MODEL_BASE_URL", "https://api.meta.ai/v1"),
        api_key=os.environ["MODEL_API_KEY"],
        timeout=60,
    )
    ok = True
    try:
        r = client.responses.create(model=model, input="Reply with only the phrase: InGather model connection successful")
        print(f"[1/2] text response: {'OK' if 'successful' in (r.output_text or '').lower() else 'UNEXPECTED TEXT'} (model={r.model})")
    except Exception as exc:
        print(f"[1/2] text response: FAIL ({type(exc).__name__})")
        return 1

    tools = [{
        "type": "function",
        "name": "get_city_time",
        "description": "Return the current local time for a city.",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"], "additionalProperties": False},
    }]
    try:
        r = client.responses.create(model=model, input="What time is it in Philadelphia? Use the tool.", tools=tools)
        calls = [i for i in r.output if i.type == "function_call"]
        if not calls:
            print("[2/2] tool round trip: FAIL (model did not call the tool)")
            return 1
        outputs = [{"type": "function_call_output", "call_id": c.call_id, "output": json.dumps({"time": "10:30 AM"})} for c in calls]
        r2 = client.responses.create(model=model, previous_response_id=r.id, input=outputs, tools=tools)
        ok = "10:30" in (r2.output_text or "")
        print(f"[2/2] tool round trip: {'OK' if ok else 'UNEXPECTED TEXT'} ({len(calls)} call(s), item types={sorted({i.type for i in r.output})})")
    except Exception as exc:
        print(f"[2/2] tool round trip: FAIL ({type(exc).__name__})")
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
