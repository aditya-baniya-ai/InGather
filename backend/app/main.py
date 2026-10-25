import importlib
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings

ROUTERS = [
    "app.api.auth",
    "app.api.plans",
    "app.api.agent",
    "app.api.proposals",
    "app.api.chats",
    "app.api.safety",
    "app.api.verification",
    "app.ai.routes",  # voice transcription, cover images
    "app.ai.connector",  # MCP endpoint for the user's own Muse agent
]


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="InGather API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_list, allow_methods=["*"], allow_headers=["*"], allow_credentials=False
    )

    @app.get("/health")
    def health():
        return {"ok": True, "ai_live": s.ai_live, "demo_mode": s.demo_mode, "model": s.meta_model}

    for name in ROUTERS:
        app.include_router(importlib.import_module(name).router)

    media = Path(s.media_dir)
    media.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=media), name="media")

    dist = Path(s.static_dir)
    if dist.is_dir():  # production: serve the built React app from the same origin
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith(("api/", "mcp")):
                raise HTTPException(404, "Not found")
            file = dist / path
            return FileResponse(file if path and file.is_file() else dist / "index.html")

    return app


app = create_app()
