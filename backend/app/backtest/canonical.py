"""Canonical JSON: one way to write a value, so equal values give equal bytes (S7.7;
doc/reference/runs.md).

A run's files, its spec hash, and its run ID all come from here
(app/backtest/records.py), so the same run always writes the same bytes.

- `canonical_json(value)` is the one text for a value: keys sorted, no spaces, UTF-8.
  With an `indent` it's the same text laid out over lines, for files a person reads
  or compares.
- `sha256_hex(value)` hashes the compact text.
- `rounded(value)` rounds every float to 12 significant digits. Results are rounded
  before they're saved, because the last digit of a power, such as CAGR's, can differ
  between machines. A spec never is: it's saved exactly as it ran.

Numbers are written as Python writes them, the shortest text that reads back as the
same float: 0.1, 1e-07, 1.5e+16. A whole float keeps its ".0", an integer has none, and
-0.0 is written 0.0. NaN and the infinities aren't JSON, and are rejected.
"""

import hashlib
import json
import math
from typing import Any

SIGNIFICANT_DIGITS = 12
"""How many significant digits a saved result keeps. A float has 15 to 17, and the
arithmetic that differs between machines differs in the last one or two."""


def canonical_json(value: Any, *, indent: int | None = None) -> str:
    """`value` as canonical JSON: compact, or indented by `indent` spaces.

    `value` must be made of JSON's own types: objects with string keys, lists (or
    tuples), strings, integers, finite floats, booleans, and None. Raises TypeError for
    anything else, such as a date, and ValueError for NaN or an infinity, each naming
    where it is.
    """
    checked = _checked(value, "value")
    if indent is None:
        return json.dumps(
            checked,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    return json.dumps(
        checked, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=indent
    )


def sha256_hex(value: Any) -> str:
    """The SHA-256 of `value`'s compact canonical JSON, in UTF-8, as 64 hex digits."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def rounded(value: Any, digits: int = SIGNIFICANT_DIGITS) -> Any:
    """`value` with every float in it rounded to `digits` significant digits.

    Objects and lists are copied, and tuples become lists. Integers, booleans, and
    everything else are left as they are.
    """
    if isinstance(value, float):
        return float(f"{value:.{digits}g}") if math.isfinite(value) else value
    if isinstance(value, dict):
        return {key: rounded(item, digits) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [rounded(item, digits) for item in value]
    return value


def _checked(value: Any, where: str) -> Any:
    """`value` as json.dumps should get it, or an error that says where it's wrong."""
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{where} is {value}, which isn't JSON")
        return value + 0.0  # -0.0 becomes 0.0
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise TypeError(f"{where} has the key {key!r}, which isn't a string")
        return {key: _checked(item, f"{where}.{key}") for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_checked(item, f"{where}[{i}]") for i, item in enumerate(value)]
    raise TypeError(f"{where} is a {type(value).__name__}, which isn't JSON")
