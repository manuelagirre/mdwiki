"""FastAPI app factory + `serve()` entry point. Own ASGI process, own port -
no in-process mounting into a host app (rejected for v1, see the extraction
item's backlog page)."""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse

from .config import SiteConfig
from .paths import is_hidden
from .render import PageNotFound, WikiRenderer, relpath_to_url
from .search import results_html, search
from .theme import DEFAULT_THEME_DIR, STATIC_DIR
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


def _change_token(roots: tuple[Path, ...]) -> str:
    """Cheap fingerprint of the files under `roots` (dot-paths skipped):
    changes whenever a file is added, removed or modified. Polled by pages
    served with `--watch`."""
    newest, count = 0, 0
    for root in roots:
        for path in root.rglob("*"):
            if is_hidden(path.relative_to(root)):
                continue
            try:
                stat = path.stat()
            except OSError:  # vanished mid-walk
                continue
            newest = max(newest, stat.st_mtime_ns)
            count += 1
    return f"{newest}-{count}"


def create_app(
    content_dir: Path,
    config_path: Path | None = None,
    widgets_dir: Path | None = None,
    *,
    search_enabled: bool = True,
    watch: bool = False,
) -> FastAPI:
    """`search_enabled=False` hides the nav search box - for `mdwiki build`,
    whose static output has no server behind `/_search`. `watch=True` makes
    every page reload itself when a content or theme file changes (see
    `_change_token`) - an authoring aid for `mdwiki serve --watch`."""
    content_dir = Path(content_dir).resolve()
    config = SiteConfig.load(config_path)
    for warning in config.warnings:
        print(f"mdwiki: warning: {warning}", file=sys.stderr)
    effective_widgets_dir = Path(widgets_dir).resolve() if widgets_dir else config.widgets_dir
    theme_path = _theme_search_path(config.theme_dir)
    renderer = WikiRenderer(content_dir, config, effective_widgets_dir)
    templates = _templates_for(theme_path)

    app = FastAPI(title=config.title)
    # Rendered pages and the theme CSS are text that compresses ~4-5x.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # Route handlers are plain `def`, not `async def`: they read files and
    # render markdown (blocking work), and FastAPI runs sync handlers in its
    # threadpool - an `async def` doing the same would run on the event
    # loop and stall every other request until it finished.

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
    def _assets(asset_path: str):
        for base in (*theme_path, STATIC_DIR):
            found = _contained_file(base, asset_path)
            if found is not None:
                return FileResponse(found)
        raise HTTPException(status_code=404, detail="asset not found")

    @app.api_route("/_widgets/{name}/{asset_path:path}", methods=["GET", "HEAD"])
    def _widget_assets(name: str, asset_path: str):
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

    def _shell_response(
        request: Request,
        title: str,
        content: str,
        *,
        back_link: dict[str, str] | None = None,
        breadcrumbs: list[dict[str, str]] | None = None,
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
                "breadcrumbs": breadcrumbs or [],
                "nav": config.nav,
                "backend_base": config.backend_base,
                "has_mermaid": has_mermaid,
                "search_enabled": search_enabled,
                "watch_token": _change_token(watched_roots) if watch else None,
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
            breadcrumbs=page.breadcrumbs,
            has_mermaid=page.has_mermaid,
        )

    def _redirect_to(request: Request, canonical: str) -> RedirectResponse:
        location = quote(canonical)
        if request.url.query:
            location += "?" + request.url.query
        return RedirectResponse(location, status_code=308)

    watched_roots = (content_dir, *theme_path, *([effective_widgets_dir] if effective_widgets_dir else []))

    if watch:

        @app.get("/_watch")
        def _watch():
            return PlainTextResponse(_change_token(watched_roots), headers={"Cache-Control": "no-store"})

    @app.api_route("/_search", methods=["GET", "HEAD"])
    def _search(request: Request, q: str = ""):
        hits = search(renderer, q)
        title = f"Search: {q}" if q.strip() else "Search"
        return _shell_response(request, title, results_html(q, hits))

    @app.api_route("/", methods=["GET", "HEAD"])
    def _index(request: Request):
        return _page(request, "")

    @app.api_route("/{url_path:path}", methods=["GET", "HEAD"])
    def _page(request: Request, url_path: str):
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
            return _shell_response(request, page.title, page.content_html, breadcrumbs=page.breadcrumbs)
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
    watch: bool = False,
) -> None:
    """Launch the wiki server. Same function the CLI's `mdwiki serve` and
    Python-module usage (`from mdwiki import serve`) both call."""
    app = create_app(
        content_dir=Path(dir),
        config_path=Path(config) if config else None,
        widgets_dir=Path(widgets) if widgets else None,
        watch=watch,
    )
    uvicorn.run(app, host=host, port=port)
