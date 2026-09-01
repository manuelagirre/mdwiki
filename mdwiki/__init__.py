"""mdwiki - serve a directory of markdown files as a wiki.

Programmatic usage: `from mdwiki import serve; serve(dir="./wiki", port=8001)`.
"""
from __future__ import annotations

from .server import serve

__all__ = ["serve"]
__version__ = "0.1.0"
