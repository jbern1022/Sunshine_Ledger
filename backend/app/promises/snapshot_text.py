"""The text of a snapshot, deterministically.

Promise items store character offsets into this text, so the function must
give the same answer for the same bytes forever. If it ever has to change,
bump TEXT_VERSION and re-extract; do not edit it in place.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString

TEXT_VERSION = 1
_BLOCKS = (
    "p", "div", "li", "ul", "ol", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "section",
    "article", "aside", "main", "blockquote", "dd", "dt", "dl", "figure", "figcaption", "pre", "hr", "td", "th",
)
_BREAK = "\u0001"  # marks a block boundary; source newlines inside a paragraph are just spaces
_DROP = ("script", "style", "noscript", "template", "svg", "iframe", "form", "nav", "footer", "header")


def snapshot_text(body: bytes) -> str:
    """Visible text of an HTML page: scripts, styles and page chrome removed,
    one line per block element, whitespace inside a line collapsed."""
    soup = BeautifulSoup(body, "html.parser")
    for tag in soup(_DROP):
        tag.decompose()
    for tag in soup.find_all(_BLOCKS):
        tag.insert_before(NavigableString(_BREAK))
        tag.insert_after(NavigableString(_BREAK))
    text = soup.get_text("")
    lines = (re.sub(r"\s+", " ", line).strip() for line in text.split(_BREAK))
    return "\n".join(line for line in lines if line)
