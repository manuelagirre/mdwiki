"""FastAPI app factory + `serve()` entry point. Own ASGI process, own port -
no in-process mounting into a host app (rejected for v1, see the extraction
item's backlog page)."""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse

from .config import SiteConfig
from .render import PageNotFound, WikiRenderer, relpath_to_url
from .theme import DEFAULT_THEME_DIR, STATIC_DIR
from .widgets import resolve_widget

_TEMPLATES_CACHE: dict[Path, object] = {}


def _templates_for(theme_dir: Path):
    from fastapi.templating import Jinja2Templates

    if theme_dir not in _TEMPLATES_CACHE:
        _TEMPLATES_CACHE[theme_dir] = Jinja2Templates(directory=str(theme_dir))
    return _TEMPLATES_CACHE[theme_dir]


def _contained_file(base: Path, rel: str) -> Path | None:
    """`base/rel` if it is a file inside `base`, else None. A path the OS
    can't even look up (NUL byte, over-long name) is also just None - a
    404, not a 500."""
    try:
        candidate = (base / rel).resolve()
        if candidate.is_relative_to(base.resolve()) and candidate.is_file():
            return candidate
    except (OSError, ValueError):
        pass
    return None


def create_app(
    content_dir: Path,
    config_path: Path | None = None,
    widgets_dir: Path | None = None,
) -> FastAPI:
    content_dir = Path(content_dir).resolve()
    config = SiteConfig.load(config_path)
    for warning in config.warnings:
        print(f"mdwiki: warning: {warning}", file=sys.stderr)
    effective_widgets_dir = Path(widgets_dir).resolve() if widgets_dir else None
    theme_dir = config.theme_dir if config.theme_dir else DEFAULT_THEME_DIR
    renderer = WikiRenderer(content_dir, config, effective_widgets_dir)
    templates = _templates_for(theme_dir)

    app = FastAPI(title=config.title)

    @app.exception_handler(PageNotFound)
    async def _not_found(request: Request, exc: PageNotFound) -> PlainTextResponse:
        return PlainTextResponse("Not found", status_code=404)

    @app.api_route("/_assets/{asset_path:path}", methods=["GET", "HEAD"])
    async def _assets(asset_path: str):
        for base in (theme_dir, STATIC_DIR):
            found = _contained_file(base, asset_path)
            if found is not None:
                return FileResponse(found)
        raise HTTPException(status_code=404, detail="asset not found")

    @app.api_route("/_widgets/{name}/{asset_path:path}", methods=["GET", "HEAD"])
    async def _widget_assets(name: str, asset_path: str):
        try:
            widget_dir = resolve_widget(name, effective_widgets_dir)
        except (OSError, ValueError):  # NUL or over-long name
            widget_dir = None
        if widget_dir is None:
            raise HTTPException(status_code=404, detail="no such widget")
        found = _contained_file(widget_dir, asset_path)
        if found is None:
            raise HTTPException(status_code=404, detail="asset not found")
        return FileResponse(found)

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

    @app.api_route("/", methods=["GET", "HEAD"])
    async def _index(request: Request):
        return _render_response(request, "")

    @app.api_route("/{url_path:path}", methods=["GET", "HEAD"])
    async def _page(request: Request, url_path: str):
        if renderer.page_exists(url_path):
            # Relative links in a page resolve against the URL it's served
            # at, so a page must only ever be served at its canonical URL:
            # `dir/index.md` at `/dir/` (not `/dir`), `page.md` at `/page`
            # (not `/page/`). Anything else redirects there - otherwise a
            # `[next](lesson-2.md)` link on `/lessons/lesson-1/` would point
            # at `/lessons/lesson-1/lesson-2` and 404.
            canonical = relpath_to_url(renderer.resolve_url(url_path))
            if "/" + url_path != canonical:
                location = quote(canonical)
                if request.url.query:
                    location += "?" + request.url.query
                return RedirectResponse(location, status_code=308)
            return _render_response(request, url_path)
        # No `.md` page here - fall back to a content-root file served raw,
        # as authored (e.g. a hand-written `.html` page or an image beside a
        # page). Still a plain 404 if that misses too.
        relpath = renderer.resolve_file(url_path)
        return FileResponse(renderer.file_path(relpath))

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
