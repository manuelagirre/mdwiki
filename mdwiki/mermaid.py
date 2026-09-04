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

_FENCE_RE = re.compile(
    r"^(?P<fence>`{3,}|~{3,}) *mermaid *\n(?P<code>.*?)\n(?P=fence) *$",
    re.DOTALL | re.MULTILINE,
)


class _MermaidPreprocessor(Preprocessor):
    def run(self, lines: list[str]) -> list[str]:
        text = "\n".join(lines)

        def _sub(m: re.Match) -> str:
            self.md.mdwiki_has_mermaid = True
            html = f'<pre class="mermaid">{escape(m.group("code"))}</pre>'
            return self.md.htmlStash.store(html)

        return _FENCE_RE.sub(_sub, text).split("\n")


class MermaidExtension(Extension):
    def extendMarkdown(self, md) -> None:  # noqa: N802 - markdown's own naming
        md.mdwiki_has_mermaid = False
        # 27: after normalize_whitespace (30), before fenced_code (25) - must
        # claim ```mermaid fences before the generic fenced-code preprocessor
        # gets to them.
        md.preprocessors.register(_MermaidPreprocessor(md), "mdwiki_mermaid", 27)
