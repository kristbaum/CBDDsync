"""
quickstatements.py

Rendering of QuickStatements 3.0 batches in the V1 (tab-separated) command format.

One command per line:

    [+|-]<entity>	<property>	<value>	[<qualifier>	<value> ...]	[<source>	<value> ...]

- <entity> is a QID, or LAST after a CREATE line.
- A "+" prefix forces a new statement even if one with the same value exists;
  a "-" prefix removes the matching statement (used for correcting errors).
- Without a prefix, QuickStatements merges into an existing statement with the
  same property and value, adding qualifiers/references — so re-running a batch
  of plain lines is harmless.
- Qualifier and reference values use the same formatting as main values;
  reference properties are written with an "S" instead of a "P" prefix.

Values must already be formatted for QuickStatements (Q-ids bare, strings
quoted via qs_string, dates as +YYYY-MM-DDT00:00:00Z/<precision>, ...).
"""

import re
from collections.abc import Iterable

Pair = tuple[str, str]


def qs_string(text: str) -> str:
    """
    Quote a string value for a V1 command.

    V1 has no escape syntax, so whitespace runs (tabs, newlines) are collapsed
    to single spaces and embedded double quotes are replaced by single quotes.
    """
    text = re.sub(r"\s+", " ", text).strip().replace('"', "'")
    return f'"{text}"'


def qs_line(
    entity: str,
    prop: str,
    value: str,
    qualifiers: Iterable[Pair] = (),
    references: Iterable[Pair] = (),
    prefix: str = "",
) -> str:
    """
    Render one V1 command.

    ``prop`` is a property ID (P…) or a term command (Len, Dde, Ade, …).
    ``references`` take property IDs (P…) and are written as S….
    ``prefix`` is "" (merge), "+" (force new statement) or "-" (remove).
    """
    if prefix not in ("", "+", "-"):
        raise ValueError(f"invalid QuickStatements prefix: {prefix!r}")
    parts = [f"{prefix}{entity}", prop, value]
    for q_prop, q_val in qualifiers:
        parts += [q_prop, q_val]
    for s_prop, s_val in references:
        parts += ["S" + s_prop.removeprefix("P"), s_val]
    return "\t".join(parts)


def write_qs_file(lines: Iterable[str], output_path: str) -> int:
    """Write V1 command lines to a .qs file. Returns the number of commands."""
    count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
            count += 1
    return count
