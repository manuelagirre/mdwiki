"""A markdown Treeprocessor that rewrites internal `<a href>` targets ending
in `.md` (or `.../index.md`) to the extension-less URLs mdwiki actually
serves - the same dual-purpose convention mkdocs-material uses: wiki authors
write plain relative links to sibling `.md` files (so the raw files still
cross-link correctly when browsed directly on GitHub), and this rewrites
them to what mdwiki's own routing expects at render time. See render.py's
`relpath_to_url` for the inverse (file relpath -> URL) this mirrors.

Only touches `<a href>` - never image `src`, since mdwiki serves no static
passthrough for the content root (see README "Routing"); an `<img>` pointing
at a sibling file isn't served by mdwiki regardless of what this rewrites.
"""
from __future__ import annotations

import re
from xml.etree.ElementTree import Element

from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

_EXTERNAL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


def rewrite_internal_href(href: str) -> str:
    """`../features/Foo.md` -> `../features/Foo`; `../features/index.md` ->
    `../features/`; anything else (external URLs, mailto:, pure `#anchor`
    links, non-.md targets) passed through unchanged."""
    if not href or href.startswith("#") or _EXTERNAL_SCHEME_RE.match(href):
        return href

    path, sep, fragment = href.partition("#")
    if path.endswith("/index.md"):
        path = path[: -len("index.md")]
    elif path == "index.md":
        path = "./"
    elif path.endswith(".md"):
        path = path[: -len(".md")]
    else:
        return href  # not a markdown-file link - leave alone
    return path + sep + fragment


class _LinkRewriteTreeprocessor(Treeprocessor):
    def run(self, root: Element) -> None:
        for el in root.iter("a"):
            href = el.get("href")
            if href is not None:
                el.set("href", rewrite_internal_href(href))


class InternalLinkExtension(Extension):
    """Registers `_LinkRewriteTreeprocessor`. Runs late (low priority) so it
    sees the final `<a>` tags other extensions (e.g. `toc`'s permalinks,
    were they enabled) may have added."""

    def extendMarkdown(self, md) -> None:  # noqa: N802 - markdown's own naming
        md.treeprocessors.register(_LinkRewriteTreeprocessor(md), "mdwiki_link_rewrite", 4)
