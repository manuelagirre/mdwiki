"""FastAPI app factory + `serve()` entry point. Own ASGI process, own port -
no in-process mounting into a host app (rejected for v1, see the extraction
item's backlog page)."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse

from .config import SiteConfig
from .render import PageNotFound, WikiRenderer, relpath_to_url
from .theme import DEFAULT_THEME_DIR, STATIC_DIR
from .search import results_html, search
from .widgets import resolve_widget

DEFAULT_FAVICON = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E"
    "%3Crect x='2' y='1' width='12' height='14' rx='2' fill='%231565c0'/%3E"
    "%3Cpath d='M5 5h6M5 8h6M5 11h4' stroke='white' stroke-width='1.3'/%3E%3C/svg%3E"
)

_TEMPLATES_CACHE: dict[tuple[Path, ...], object] = {}


def _theme_search_path(theme_dir: Path | None) -> tuple[Path, ...]:
    """A custom theme is overlaid on the default one, file by file: a theme
    that only ships `app.css` still gets the default `page.html`, and one
    that only ships `page.html` can still link `/_assets/app.css`."""
    if theme_dir is None or theme_dir == DEFAULT_THEME_DIR:
        return (DEFAULT_THEME_DIR,)
    return (theme_dir, DEFAULT_THEME_DIR)


def _templates_for(search_path: tuple[Path, ...]):
    from fastapi.templating import Jinja2Templates

    if search_path not in _TEMPLATES_CACHE:
        _TEMPLATES_CACHE[search_path] = Jinja2Templates(directory=[str(p) for p in search_path])
    return _TEMPLATES_CACHE[search_path]


def create_app(
    content_dir: Path,
    config_path: Path | None = None,
    widgets_dir: Path | None = None,
) -> FastAPI:
    content_dir = Path(content_dir).resolve()
    config = SiteConfig.load(config_path)
    effective_widgets_dir = Path(widgets_dir).resolve() if widgets_dir else config.widgets_dir
    theme_path = _theme_search_path(config.theme_dir)
    renderer = WikiRenderer(content_dir, config, effective_widgets_dir)
    templates = _templates_for(theme_path)

    app = FastAPI(title=config.title)

    @app.exception_handler(PageNotFound)
    async def _not_found(request: Request, exc: PageNotFound):
        # Byte-identical body for every miss (missing page, traversal
        # attempt, excluded file), so a 404 never hints which case it was.
        # Rendered in the normal page shell so the reader keeps the nav and
        # a way back, rather than a dead-end text page.
        content = (
            '<h1 id="page-not-found">Page not found</h1>\n'
            "<p>There is no page at this address.</p>\n"
            '<p><a href="/">Go to the home page</a></p>'
        )
        try:
            return _shell_response(request, "Page not found", content, status_code=404)
        except Exception:  # a broken custom template must not turn 404s into 500s
            return PlainTextResponse("Not found", status_code=404)

    @app.api_route("/_assets/{asset_path:path}", methods=["GET", "HEAD"])
    async def _assets(asset_path: str):
        for base in (*theme_path, STATIC_DIR):
            candidate = (base / asset_path).resolve()
            if candidate.is_relative_to(base.resolve()) and candidate.is_file():
                return FileResponse(candidate)
        raise HTTPException(status_code=404, detail="asset not found")

    @app.api_route("/_widgets/{name}/{asset_path:path}", methods=["GET", "HEAD"])
    async def _widget_assets(name: str, asset_path: str):
        widget_dir = resolve_widget(name, effective_widgets_dir)
        if widget_dir is None:
            raise HTTPException(status_code=404, detail="no such widget")
        candidate = (widget_dir / asset_path).resolve()
        if not candidate.is_relative_to(widget_dir.resolve()) or not candidate.is_file():
            raise HTTPException(status_code=404, detail="asset not found")
        return FileResponse(candidate)

    def _shell_response(
        request: Request,
        title: str,
        content: str,
        *,
        back_link: dict[str, str] | None = None,
        has_mermaid: bool = False,
        status_code: int = 200,
    ):
        return templates.TemplateResponse(
            request=request,
            name="page.html",
            status_code=status_code,
            context={
                "site_title": config.title,
                "title": title,
                "content": content,
                "back_link": back_link,
                "nav": config.nav,
                "backend_base": config.backend_base,
                "has_mermaid": has_mermaid,
                "request_path": request.url.path,
                # The content root's own favicon.ico if it has one (served
                # raw like any other file), else a small built-in icon -
                # either way the browser stops logging a 404 per page view.
                "favicon": "/favicon.ico" if (content_dir / "favicon.ico").is_file() else DEFAULT_FAVICON,
            },
        )

    def _render_response(request: Request, url_path: str):
        page = renderer.render_url(url_path)
        return _shell_response(
            request,
            page.title,
            page.content_html,
            back_link=page.back_link,
            has_mermaid=page.has_mermaid,
        )

    def _redirect_to(request: Request, canonical: str) -> RedirectResponse:
        location = quote(canonical)
        if request.url.query:
            location += "?" + request.url.query
        return RedirectResponse(location, status_code=308)

    @app.api_route("/_search", methods=["GET", "HEAD"])
    async def _search(request: Request, q: str = ""):
        hits = search(renderer, q)
        title = f"Search: {q}" if q.strip() else "Search"
        return _shell_response(request, title, results_html(q, hits))

    @app.api_route("/", methods=["GET", "HEAD"])
    async def _index(request: Request):
        return await _page(request, "")

    @app.api_route("/{url_path:path}", methods=["GET", "HEAD"])
    async def _page(request: Request, url_path: str):
        # Relative links in a page resolve against the URL it's served at,
        # so a page must only ever be served at its canonical URL:
        # `dir/index.md` at `/dir/` (not `/dir`), `page.md` at `/page` (not
        # `/page/`). Anything else redirects there - otherwise a
        # `[next](lesson-2.md)` link on `/lessons/lesson-1/` would point at
        # `/lessons/lesson-1/lesson-2` and 404.
        if renderer.page_exists(url_path):
            # `/` is always canonical for whatever serves the root (index.md
            # or the `index:` override, which is served *at* `/`).
            canonical = relpath_to_url(renderer.resolve_url(url_path)) if url_path else "/"
            if "/" + url_path != canonical:
                return _redirect_to(request, canonical)
            return _render_response(request, url_path)
        # A directory without its own index page gets a generated listing.
        dir_relpath = renderer.listing_dir(url_path)
        if dir_relpath is not None:
            canonical = f"/{dir_relpath}/" if dir_relpath else "/"
            if "/" + url_path != canonical:
                return _redirect_to(request, canonical)
            page = renderer.render_listing(dir_relpath)
            return _shell_response(request, page.title, page.content_html)
        # No page here - fall back to a content-root file served raw, as
        # authored (e.g. a hand-written `.html` page or an image beside a
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
