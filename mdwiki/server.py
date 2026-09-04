"""FastAPI app factory + `serve()` entry point. Own ASGI process, own port -
no in-process mounting into a host app (rejected for v1, see the extraction
item's backlog page)."""
from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse

from .config import SiteConfig
from .render import PageNotFound, WikiRenderer
from .theme import DEFAULT_THEME_DIR, STATIC_DIR
from .widgets import resolve_widget

_TEMPLATES_CACHE: dict[Path, object] = {}


def _templates_for(theme_dir: Path):
    from fastapi.templating import Jinja2Templates

    if theme_dir not in _TEMPLATES_CACHE:
        _TEMPLATES_CACHE[theme_dir] = Jinja2Templates(directory=str(theme_dir))
    return _TEMPLATES_CACHE[theme_dir]


def create_app(
    content_dir: Path,
    config_path: Path | None = None,
    widgets_dir: Path | None = None,
) -> FastAPI:
    content_dir = Path(content_dir).resolve()
    config = SiteConfig.load(config_path)
    effective_widgets_dir = Path(widgets_dir).resolve() if widgets_dir else None
    theme_dir = config.theme_dir if config.theme_dir else DEFAULT_THEME_DIR
    renderer = WikiRenderer(content_dir, config, effective_widgets_dir)
    templates = _templates_for(theme_dir)

    app = FastAPI(title=config.title)

    @app.exception_handler(PageNotFound)
    async def _not_found(request: Request, exc: PageNotFound) -> PlainTextResponse:
        return PlainTextResponse("Not found", status_code=404)

    @app.get("/_assets/{asset_path:path}")
    async def _assets(asset_path: str):
        for base in (theme_dir, STATIC_DIR):
            candidate = (base / asset_path).resolve()
            if candidate.is_relative_to(base.resolve()) and candidate.is_file():
                return FileResponse(candidate)
        raise HTTPException(status_code=404, detail="asset not found")

    @app.get("/_widgets/{name}/{asset_path:path}")
    async def _widget_assets(name: str, asset_path: str):
        widget_dir = resolve_widget(name, effective_widgets_dir)
        if widget_dir is None:
            raise HTTPException(status_code=404, detail="no such widget")
        candidate = (widget_dir / asset_path).resolve()
        if not candidate.is_relative_to(widget_dir.resolve()) or not candidate.is_file():
            raise HTTPException(status_code=404, detail="asset not found")
        return FileResponse(candidate)

    def _render_response(request: Request, url_path: str):
        page = renderer.render_url(url_path)
        return templates.TemplateResponse(
            request=request,
            name="page.html",
            context={
                "site_title": config.title,
                "title": page.title,
                "content": page.content_html,
                "back_link": page.back_link,
                "nav": config.nav,
                "backend_base": config.backend_base,
                "has_mermaid": page.has_mermaid,
                "request_path": request.url.path,
            },
        )

    @app.get("/")
    async def _index(request: Request):
        return _render_response(request, "")

    @app.get("/{url_path:path}")
    async def _page(request: Request, url_path: str):
        return _render_response(request, url_path)

    return app


def serve(
    dir: str | Path,
    port: int = 8000,
    config: str | Path | None = None,
    widgets: str | Path | None = None,
    host: str = "127.0.0.1",
) -> None:
    """Launch the wiki server. Same function the CLI's `mdwiki serve` and
    Python-module usage (`from mdwiki import serve`) both call."""
    app = create_app(
        content_dir=Path(dir),
        config_path=Path(config) if config else None,
        widgets_dir=Path(widgets) if widgets else None,
    )
    uvicorn.run(app, host=host, port=port)
