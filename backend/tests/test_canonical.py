"""Canonical JSON (S7.7): one text for a value, so equal values give equal bytes and
hashes (app/backtest/canonical.py)."""

import hashlib
import math
from datetime import date
from typing import Any

import pytest

from app.backtest.canonical import canonical_json, rounded, sha256_hex


def test_keys_are_sorted_at_every_level() -> None:
    value = {"b": {"z": 1, "a": 2}, "a": [{"d": 3, "c": 4}]}

    assert canonical_json(value) == '{"a":[{"c":4,"d":3}],"b":{"a":2,"z":1}}'


def test_the_order_a_value_was_built_in_doesnt_change_its_text() -> None:
    one = {"spec": {"name": "x", "costs": 10.0}, "data_version": "v"}
    other = {"data_version": "v", "spec": {"costs": 10.0, "name": "x"}}

    assert canonical_json(one) == canonical_json(other)
    assert sha256_hex(one) == sha256_hex(other)


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (1, "1"),
        (1.0, "1.0"),  # a whole float keeps its ".0"
        (-0.0, "0.0"),
        (0.1, "0.1"),
        (0.1 + 0.2, "0.30000000000000004"),  # exact: rounding is `rounded`'s job
        (1e-7, "1e-07"),
        (1.5e16, "1.5e+16"),
        (-2.5, "-2.5"),
        (True, "true"),
        (None, "null"),
        ("é ✓", '"é ✓"'),  # UTF-8, not \u escapes
        ((1, 2), "[1,2]"),  # a tuple is a list
    ],
)
def test_each_value_has_one_text(value: Any, text: str) -> None:
    assert canonical_json(value) == text


def test_an_indent_lays_the_same_text_out_over_lines() -> None:
    value = {"b": [1, 2], "a": {"c": 0.5}}

    assert canonical_json(value, indent=2) == (
        '{\n  "a": {\n    "c": 0.5\n  },\n  "b": [\n    1,\n    2\n  ]\n}'
    )


@pytest.mark.parametrize(
    ("value", "error", "message"),
    [
        (math.nan, ValueError, "value is nan, which isn't JSON"),
        ({"a": [1.0, math.inf]}, ValueError, r"value\.a\[1\] is inf"),
        ({"day": date(2020, 6, 1)}, TypeError, r"value\.day is a date"),
        ({"a": {1: "x"}}, TypeError, r"value\.a has the key 1, which isn't a string"),
        ([{1, 2}], TypeError, r"value\[0\] is a set"),
    ],
)
def test_what_isnt_json_is_rejected_by_name(
    value: Any, error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        canonical_json(value)


def test_the_hash_is_of_the_compact_text_in_utf8() -> None:
    assert sha256_hex({"a": 1}) == hashlib.sha256(b'{"a":1}').hexdigest()
    assert sha256_hex("é") == hashlib.sha256('"é"'.encode()).hexdigest()


def test_rounding_keeps_twelve_significant_digits() -> None:
    assert rounded(0.1 + 0.2) == 0.3
    assert rounded(1 / 3) == 0.333333333333
    assert rounded(123456789.123456789) == 123456789.123
    assert rounded(-2 / 3e9) == -6.66666666667e-10
    assert rounded(0.0) == 0.0


def test_rounding_hides_a_last_digit_that_differs_between_machines() -> None:
    # A power's last digit isn't the same on every machine (S7.6): CAGR is one.
    here = 1.2355 ** (1 / 2.99)
    elsewhere = math.nextafter(here, math.inf)

    assert here != elsewhere
    assert rounded(here) == rounded(elsewhere)
    assert canonical_json(rounded(here)) == canonical_json(rounded(elsewhere))


def test_rounding_reaches_every_float_and_nothing_else() -> None:
    value = {"a": [1 / 3, (2 / 3, 7)], "b": {"c": 1 / 7, "d": "1/3", "e": None}}

    assert rounded(value) == {
        "a": [0.333333333333, [0.666666666667, 7]],
        "b": {"c": 0.142857142857, "d": "1/3", "e": None},
    }
    assert rounded(True) is True
    assert rounded(10**20) == 10**20  # an integer is exact
    assert value["a"][1] == (2 / 3, 7)  # the value given isn't changed
