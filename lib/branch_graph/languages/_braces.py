"""Type declarations and their brace-matched extent, for brace languages. Not a language: `_` keeps the registry out."""

from __future__ import annotations

import re

# Strings and comments, blanked before braces are counted: a `}` inside either would end a type early.
NOISE = re.compile(r'"""[\s\S]*?"""|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|//[^\n]*|/\*[\s\S]*?\*/|#[^\n]*')


def _blank(source: str) -> str:
    return NOISE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), source)


# ponytail: a regex and a brace count, not a parser. A brace inside string interpolation, or a heredoc, can end a type
# early. Upgrade path: the language's own parser (swift-syntax, nikic/php-parser), if attribution looks wrong in review.
def ranges(source: str, decl: re.Pattern) -> list[tuple[str, int, int]]:
    """(name, first line, last line) for each match of `decl` (group 1 = the name) followed by a `{…}` body."""
    text, out = _blank(source), []
    for m in decl.finditer(text):
        start = text.find("{", m.end())
        if start < 0 or ";" in text[m.end():start]:
            continue
        depth, end = 0, len(text) - 1
        for i in range(start, len(text)):
            depth += (text[i] == "{") - (text[i] == "}")
            if depth == 0:
                end = i
                break
        out.append((m.group(1), text.count("\n", 0, m.start()) + 1, text.count("\n", 0, end) + 1))
    return out
