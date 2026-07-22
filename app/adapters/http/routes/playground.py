"""
Playground route — serves the interactive inference testing UI.

Mounts static assets (HTML, JS, CSS) at /playground.
No authentication required to load the UI itself.
"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from starlette.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "static" / "playground"

router = APIRouter()


@router.get("/playground", response_class=HTMLResponse, include_in_schema=False)
async def playground_index():
    """Serve the playground HTML page."""
    index_path = STATIC_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


def mount_playground(app):
    """Mount playground static files on the FastAPI app instance."""
    app.mount(
        "/playground",
        StaticFiles(directory=str(STATIC_DIR), html=True),
        name="playground",
    )
