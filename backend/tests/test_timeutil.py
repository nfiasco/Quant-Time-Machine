from datetime import UTC, date, datetime, time

import pytest

from app.data.timeutil import (
    ET,
    KnowledgeTimeError,
    market_time,
    parse_knowledge_time,
    to_utc,
)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_bare_date_means_0930_eastern() -> None:
    assert parse_knowledge_time("2020-06-05") == utc(2020, 6, 5, 13, 30)  # EDT, UTC-4
    assert parse_knowledge_time("2020-01-15") == utc(2020, 1, 15, 14, 30)  # EST, UTC-5


def test_no_offset_timestamp_means_eastern() -> None:
    assert parse_knowledge_time("2020-06-05T09:30") == utc(2020, 6, 5, 13, 30)
    assert parse_knowledge_time("2020-06-05T08:00") == utc(2020, 6, 5, 12, 0)
    assert parse_knowledge_time("2020-01-15T09:30:00") == utc(2020, 1, 15, 14, 30)


def test_no_offset_timestamp_in_dst_change_hours() -> None:
    # 01:30 happened twice on 2020-11-01, at 05:30Z (EDT) and 06:30Z (EST): the later one wins.
    assert parse_knowledge_time("2020-11-01T01:30") == utc(2020, 11, 1, 6, 30)
    # Clocks jumped from 02:00 to 03:00 on 2020-03-08, so 02:30 never happened.
    with pytest.raises(KnowledgeTimeError, match="doesn't exist"):
        parse_knowledge_time("2020-03-08T02:30")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2020-06-05T09:30-04:00", utc(2020, 6, 5, 13, 30)),
        ("2020-06-05T09:30:00-04:00", utc(2020, 6, 5, 13, 30)),
        ("2020-06-05T13:30Z", utc(2020, 6, 5, 13, 30)),
        ("2020-06-05T13:30:00+00:00", utc(2020, 6, 5, 13, 30)),
        ("2020-06-05T15:30+02:00", utc(2020, 6, 5, 13, 30)),
        ("2020-04-30T22:03:10.5Z", utc(2020, 4, 30, 22, 3, 10, 500000)),
    ],
)
def test_timestamp_with_offset_is_used_as_given(text: str, expected: datetime) -> None:
    assert parse_knowledge_time(text) == expected


@pytest.mark.parametrize(
    "text", ["2020-06-05", "2020-06-05T09:30", "2020-06-05T09:30-04:00"]
)
def test_result_is_aware_utc(text: str) -> None:
    assert parse_knowledge_time(text).tzinfo is UTC


def test_bare_date_is_not_snapped_to_a_trading_day() -> None:
    # A Saturday and a holiday still mean 09:30 ET that day (rule 3).
    assert parse_knowledge_time("2020-06-06") == utc(2020, 6, 6, 13, 30)
    assert parse_knowledge_time("2020-12-25") == utc(2020, 12, 25, 14, 30)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "now",
        " 2020-06-05",
        "2020-6-5",
        "2020-02-30",
        "2020-13-01",
        "06/05/2020",
        "2020-W23-5",
        "20200605",
        "2020-06-05 09:30",
        "2020-06-05t09:30",
        "2020-06-05T9:30",
        "2020-06-05T25:00",
        "2020-06-05T09:30+0400",
        "2020-06-05T09:30:00.1234567Z",
        "0001-01-01T00:00+01:00",
    ],
)
def test_invalid_knowledge_times_are_rejected(text: str) -> None:
    with pytest.raises(KnowledgeTimeError):
        parse_knowledge_time(text)


def test_decoded_plus_sign_gets_a_hint() -> None:
    # In a URL query string, an unencoded "+00:00" arrives as " 00:00".
    with pytest.raises(KnowledgeTimeError, match="%2B"):
        parse_knowledge_time("2020-06-05T13:30:00 00:00")


def test_market_time_follows_daylight_saving() -> None:
    assert market_time(date(2020, 6, 4), time(16)) == utc(2020, 6, 4, 20)
    assert market_time(date(2020, 11, 27), time(13)) == utc(2020, 11, 27, 18)
    assert market_time(date(1990, 2, 2), time(8, 30)) == utc(1990, 2, 2, 13, 30)


def test_to_utc_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="naive"):
        to_utc(datetime(2020, 6, 5, 9, 30))  # noqa: DTZ001 (naive on purpose)
    assert to_utc(datetime(2020, 6, 5, 9, 30, tzinfo=ET)) == utc(2020, 6, 5, 13, 30)
