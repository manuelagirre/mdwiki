"""Full-text search over the content root's `.md` pages, behind
`GET /_search?q=...`. No index, no dependencies: every query reads the
pages fresh (the same as page rendering does), which keeps results in sync
with the files on disk and is plenty fast for wiki-sized trees.

A page matches when every query term occurs in its title or text (case-
insensitive). Title hits rank above body-only hits; ties break on how
often the terms occur, then on path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from urllib.parse import quote

from .render import WikiRenderer, relpath_to_url

MAX_RESULTS = 50
_SNIPPET_RADIUS = 80

# Rough markdown -> plain text, good enough for matching and snippets:
# drop code fences' markers, link targets, emphasis/heading punctuation and
# widget macros, keep the words.
_MACRO_RE = re.compile(r"\{\{\s*widget:.*?\}\}", re.DOTALL)
_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_PUNCT_RE = re.compile(r"[#*_`>|~]+|:?-{3,}:?|<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def _plain_text(markdown_body: str) -> str:
    text = _MACRO_RE.sub(" ", markdown_body)
    text = _LINK_RE.sub(r"\1", text)
    text = _PUNCT_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


@dataclass
class SearchHit:
    relpath: str
    url: str
    title: str
    snippet_html: str
    score: tuple


def _snippet_html(text: str, terms: list[str]) -> str:
    lower = text.lower()
    first = min((i for i in (lower.find(t) for t in terms) if i >= 0), default=0)
    start = max(0, first - _SNIPPET_RADIUS)
    end = min(len(text), first + _SNIPPET_RADIUS)
    # Snap to word boundaries so the snippet doesn't open or close mid-word.
    if start > 0:
        space = text.find(" ", start, first)
        start = space + 1 if space != -1 else start
    if end < len(text):
        space = text.rfind(" ", first, end)
        end = space if space > first else end
    window = text[start:end]
    pattern = re.compile("|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)), re.IGNORECASE)
    pieces: list[str] = []
    pos = 0
    for m in pattern.finditer(window):
        pieces.append(escape(window[pos : m.start()]))
        pieces.append(f"<mark>{escape(m.group(0))}</mark>")
        pos = m.end()
    pieces.append(escape(window[pos:]))
    return ("…" if start > 0 else "") + "".join(pieces) + ("…" if end < len(text) else "")


def _pages(root: Path) -> list[str]:
    return sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*.md")
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(root).parts)
    )


def search(renderer: WikiRenderer, query: str) -> list[SearchHit]:
    # Normalized like the page text, so `widget_markup` or `**bold**`
    # in a query still lines up with what the pages were reduced to.
    terms = _plain_text(query).lower().split()
    if not terms:
        return []
    hits: list[SearchHit] = []
    for relpath in _pages(renderer.root):
        try:
            title, body = renderer.page_source(relpath)
        except Exception:
            continue
        text = _plain_text(body)
        title_l, text_l = title.lower(), text.lower()
        if not all(t in title_l or t in text_l for t in terms):
            continue
        title_hits = sum(t in title_l for t in terms)
        occurrences = sum(text_l.count(t) for t in terms)
        hits.append(
            SearchHit(
                relpath=relpath,
                url=relpath_to_url(relpath),
                title=title,
                snippet_html=_snippet_html(text, terms),
                score=(-title_hits, -occurrences, relpath),
            )
        )
    hits.sort(key=lambda h: h.score)
    return hits[:MAX_RESULTS]


def results_html(query: str, hits: list[SearchHit]) -> str:
    """The content region of the search results page."""
    q = escape(query, quote=True)
    parts = [
        '<h1 id="search">Search</h1>',
        '<form class="mdwiki-search-form" action="/_search" method="get" role="search">'
        f'<input type="search" name="q" value="{q}" aria-label="Search the wiki" autofocus> '
        '<button type="submit">Search</button></form>',
    ]
    if not query.strip():
        return "\n".join(parts)
    if not hits:
        parts.append(f"<p>No pages match <strong>{escape(query)}</strong>.</p>")
        return "\n".join(parts)
    noun = "page" if len(hits) == 1 else "pages"
    more = "+" if len(hits) == MAX_RESULTS else ""
    parts.append(f"<p>{len(hits)}{more} {noun} match <strong>{escape(query)}</strong>.</p>")
    parts.append('<ol class="mdwiki-search-results">')
    for hit in hits:
        parts.append(
            f'<li><a href="{escape(quote(hit.url), quote=True)}">{escape(hit.title)}</a>'
            f'<div class="mdwiki-search-path">{escape(hit.url)}</div>'
            f'<p class="mdwiki-search-snippet">{hit.snippet_html}</p></li>'
        )
    parts.append("</ol>")
    return "\n".join(parts)
