"""Renders ```mermaid fenced code blocks as diagrams by default - no widget,
no macro, just the plain fence syntax already used elsewhere in markdown.

Runs as a markdown Preprocessor, ahead of `fenced_code` (see MD_EXTENSIONS
in render.py), so it claims ```mermaid fences before the generic
fenced-code/codehilite path can turn them into a syntax-highlighted,
HTML-escaped `<pre><code>` block. Rewrites straight to
`<pre class="mermaid">RAW_SOURCE</pre>` - the shape mermaid.js's
`mermaid.run({querySelector: ".mermaid"})` expects (it reads the *rendered
DOM text* of matching elements, so mermaid syntax like `A->>B: hi` needs to
survive as literal characters once the browser parses the HTML - hence the
plain `html.escape()` below, not raw interpolation: entities decode back to
the original characters when the browser computes `.textContent`, same as
any other HTML text node).

Sets `md.mdwiki_has_mermaid = True` when at least one fence was found, so
render.py/server.py can skip loading mermaid.js on pages that don't need it.
See theme/page.html.
"""
from __future__ import annotations

import re
from html import escape

from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor

# A backtick fence's info string can't contain a backtick (CommonMark, and
# fenced_code agrees): "```foo``` text" is inline code, not an opener.
_OPEN_RE = re.compile(r"^(?P<fence>`{3,}(?=[^`]*$)|~{3,})(?P<info>.*)$")
_MERMAID_INFO_RE = re.compile(r"^ *mermaid *$")


class _MermaidPreprocessor(Preprocessor):
    """Walks the document fence by fence rather than regex-matching
    ```mermaid anywhere: a mermaid fence that is itself *content* of an
    outer code block (e.g. a ````markdown block documenting the syntax)
    must stay literal code, not become a live diagram. Closing fences
    match the opener exactly, as in Python-Markdown's fenced_code."""

    def run(self, lines: list[str]) -> list[str]:
        out: list[str] = []
        i = 0
        while i < len(lines):
            m = _OPEN_RE.match(lines[i])
            if not m:
                out.append(lines[i])
                i += 1
                continue
            fence = m.group("fence")
            close = next(
                (j for j in range(i + 1, len(lines)) if lines[j].rstrip(" ") == fence),
                None,
            )
            if close is None:  # unterminated - not a fence, leave as text
                out.append(lines[i])
                i += 1
                continue
            if _MERMAID_INFO_RE.match(m.group("info")):
                self.md.mdwiki_has_mermaid = True
                code = "\n".join(lines[i + 1 : close])
                # Blank lines around the placeholder (as fenced_code does) so a
                # fence right under a paragraph line isn't swallowed into <p>.
                out.extend(["", self.md.htmlStash.store(f'<pre class="mermaid">{escape(code)}</pre>'), ""])
            else:
                out.extend(lines[i : close + 1])  # someone else's block: untouched
            i = close + 1
        return out


class MermaidExtension(Extension):
    def extendMarkdown(self, md) -> None:  # noqa: N802 - markdown's own naming
        md.mdwiki_has_mermaid = False
        # 27: after normalize_whitespace (30), before fenced_code (25) - must
        # claim ```mermaid fences before the generic fenced-code preprocessor
        # gets to them.
        md.preprocessors.register(_MermaidPreprocessor(md), "mdwiki_mermaid", 27)
