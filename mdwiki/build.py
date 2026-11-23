"""`mdwiki build` - export the wiki as static files, for GitHub Pages,
Netlify, S3 or any plain web server.

Every page is fetched from the real app (called in-process as an ASGI app), so the output is exactly what `mdwiki serve` returns - same
rendering, widgets, listings and 404 page - rather than a second renderer
that could drift. URLs keep their served shape:

- `page.md`        -> `page.html`        (served at `/page` by static hosts
                                          that resolve extensionless URLs,
                                          as GitHub Pages and Netlify do)
- `dir/index.md`   -> `dir/index.html`   (served at `/dir/`)
- listing for dir/ -> `dir/index.html`
- raw files        -> copied as-is, same path
- theme assets     -> `_assets/`, widgets in use -> `_widgets/<name>/`
- the 404 page     -> `404.html`

Search needs the server, so the nav search box is left out of the export.
"""
from __future__ import annotations

import asyncio
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from .config import SiteConfig
from .ordering import has_pages
from .render import PageNotFound, WikiRenderer, relpath_to_url
from .server import _theme_search_path, create_app
from .theme import STATIC_DIR
from .widgets import resolve_widget

MARKER = ".mdwiki-build"
"""Dropped into the output directory, so a rebuild may safely clear it -
mdwiki never deletes a directory it didn't create."""

_WIDGET_RE = re.compile(r'data-widget="([A-Za-z0-9_-]+)"')
_SKIP_ASSET_NAMES = {"page.html", "__init__.py", "__pycache__"}


class BuildError(Exception):
    pass


@dataclass
class _Response:
    status: int
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def _fetch(app, url: str) -> _Response:
    """GET `url` from the ASGI app in-process - a minimal client, so build
    needs nothing beyond mdwiki's own runtime dependencies."""
    path = url.split("?", 1)[0]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": quote(path).encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"localhost")],
        "client": ("127.0.0.1", 0),
        "server": ("localhost", 80),
    }
    status = 0
    chunks: list[bytes] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    asyncio.run(app(scope, receive, send))
    return _Response(status, b"".join(chunks))


def _is_dot_path(rel: Path) -> bool:
    return any(part.startswith(".") for part in rel.parts)


def _output_path(out: Path, url: str) -> Path:
    if url == "/":
        return out / "index.html"
    if url.endswith("/"):
        return out / url.strip("/") / "index.html"
    return out / (url.lstrip("/") + ".html")


def _prepare_out_dir(out: Path, content_dir: Path) -> None:
    out = out.resolve()
    if out == content_dir or out.is_relative_to(content_dir):
        raise BuildError(f"output directory {out} is inside the content root - it would be served as content")
    if out.exists():
        if not out.is_dir():
            raise BuildError(f"{out} exists and is not a directory")
        if any(out.iterdir()):
            if not (out / MARKER).is_file():
                raise BuildError(f"{out} is not empty and wasn't created by mdwiki build - refusing to overwrite it")
            shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / MARKER).write_text("Created by `mdwiki build`; safe to delete.\n", encoding="utf-8")


def _copy_tree(src: Path, dest: Path) -> None:
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        if not path.is_file() or _is_dot_path(rel) or _SKIP_ASSET_NAMES & set(rel.parts):
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def build(
    content_dir: Path,
    out_dir: Path,
    config_path: Path | None = None,
    widgets_dir: Path | None = None,
) -> int:
    """Export the site; returns the number of HTML pages written."""
    content_dir = Path(content_dir).resolve()
    out = Path(out_dir).resolve()
    # Load the config (raising on a broken one) before touching --out, so a
    # typo in mdwiki.yml can't wipe the previous good export.
    app = create_app(content_dir, config_path, widgets_dir, search_enabled=False)
    config = SiteConfig.load(config_path)
    _prepare_out_dir(out, content_dir)

    effective_widgets_dir = Path(widgets_dir).resolve() if widgets_dir else config.widgets_dir
    renderer = WikiRenderer(content_dir, config, effective_widgets_dir)

    # Every URL that renders a page: each .md file, `/`, and a listing for
    # each page-holding directory without its own index.md.
    urls = {"/"}
    for path in content_dir.rglob("*"):
        rel = path.relative_to(content_dir)
        if _is_dot_path(rel):
            continue
        if path.is_file() and path.suffix == ".md":
            urls.add(relpath_to_url(rel.as_posix()))
        elif path.is_dir() and not (path / "index.md").is_file() and has_pages(path):
            urls.add("/" + rel.as_posix() + "/")

    widgets_used: set[str] = set()
    written: dict[Path, str] = {}
    for url in sorted(urls):
        res = _fetch(app, url)
        if res.status != 200:
            raise BuildError(f"{url}: server answered {res.status}")
        target = _output_path(out, url)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(res.body)
        written[target] = url
        widgets_used.update(_WIDGET_RE.findall(res.text))

    not_found = _fetch(app, "/_mdwiki-build-404")
    (out / "404.html").write_bytes(not_found.body)
    widgets_used.update(_WIDGET_RE.findall(not_found.text))

    # Raw files (images, author-written .html, ...) exactly as the server
    # would serve them - the same exclusions apply (.md sources, _order.yml).
    for path in content_dir.rglob("*"):
        rel = path.relative_to(content_dir)
        if not path.is_file() or _is_dot_path(rel):
            continue
        try:
            renderer.resolve_file(rel.as_posix())
        except PageNotFound:
            continue
        target = out / rel
        if target in written:
            raise BuildError(
                f"{rel} and the page served at {written[target]} would both be written to "
                f"{target.relative_to(out)} - rename one of them"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)

    # Theme assets, lowest priority first so a custom theme's files win -
    # the same lookup order as the server's /_assets/ route.
    for base in (STATIC_DIR, *reversed(_theme_search_path(config.theme_dir))):
        _copy_tree(base, out / "_assets")

    for name in sorted(widgets_used):
        widget_dir = resolve_widget(name, effective_widgets_dir)
        if widget_dir is not None:
            _copy_tree(widget_dir, out / "_widgets" / name)

    return len(urls)
