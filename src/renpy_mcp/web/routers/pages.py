"""Page routes — static HTML pages served by the dashboard."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import fastapi_app as _fa

router = APIRouter()


@router.get("/")
async def root():
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/dashboard")


@router.get("/dashboard")
async def dashboard():
    return FileResponse(_fa.DASHBOARD_DIR / "index.html")


@router.get("/dashboard/{path:path}")
async def dashboard_fallback(path: str):
    """SPA fallback for React Router deep links."""
    dashboard_root = _fa.DASHBOARD_DIR.resolve()
    candidate = (dashboard_root / path).resolve()
    try:
        candidate.relative_to(dashboard_root)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")

    if candidate.exists() and candidate.is_file():
        return FileResponse(candidate)

    STATIC_EXTS = {
        ".js", ".css", ".svg", ".png", ".jpg", ".jpeg",
        ".webp", ".gif", ".ico", ".map", ".woff", ".woff2",
        ".ttf", ".eot", ".json", ".xml", ".pdf", ".zip",
    }
    if candidate.suffix.lower() in STATIC_EXTS:
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(dashboard_root / "index.html")


@router.get("/story-map")
async def story_map():
    return FileResponse(_fa.STATIC_DIR / "story_map.html")


@router.get("/script-editor")
async def script_editor():
    return FileResponse(_fa.STATIC_DIR / "script_editor.html")


@router.get("/heatmap")
async def heatmap():
    return FileResponse(_fa.STATIC_DIR / "heatmap.html")


@router.get("/assets")
async def assets_page():
    return FileResponse(_fa.STATIC_DIR / "asset_manager.html")
