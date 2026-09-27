"""Deterministic medication schedule generation.

Schedules are created only from doctor-confirmed medication instructions.

Supported:
- English frequency terminology
- Common Urdu frequency terminology
- Common Punjabi Shahmukhi frequency terminology
- English / Urdu duration wording
- PRN / as-needed medication
- Fixed daily counts
- Named times
- Every-N-hours schedules

No dose, frequency or duration is invented. Unsupported or ambiguous
instructions return an explicit review error.
"""

from __future__ import annotations

import re

from datetime import (
    date,
    datetime,
    time,
    timedelta,
)

from zoneinfo import ZoneInfo


# ============================================================
# DIGIT NORMALISATION
# ============================================================

# Medication instructions may contain Western, Arabic-Indic or Urdu-style digits.
# This mapping converts them into the same numeric form before duration and
# frequency parsing so the later scheduling rules can handle them consistently.

DIGIT_TRANSLATION = str.maketrans(
    {
        # Arabic-Indic
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",

        # Eastern Arabic / Urdu
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
    }
)

# This helper normalises doctor-confirmed instruction text before it is parsed.
# It converts supported digit styles, lowercases the text and removes unnecessary
# spacing or punctuation without changing the meaning of the instruction.
def _normalise(
    value: str | None,
) -> str:

    text = (
        value
        or ""
    ).translate(
        DIGIT_TRANSLATION
    )

    text = text.lower()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip(
        " .،,"
    )


# ============================================================
# DURATION
# ============================================================
# These patterns and number mappings recognise medication durations written in
# different forms, including numeric values, English number words, shortened
# units, fortnights and the existing Urdu duration wording.
EN_DURATION_RE = re.compile(
    r"\b(\d+)\s*"
    r"(day|days|week|weeks|month|months)\b",
    re.I,
)

AR_DURATION_RE = re.compile(
    r"(\d+)\s*"
    r"(دن|دنوں|ہفتہ|ہفتے|ہفتوں|"
    r"مہینہ|مہینے|مہینوں)"
)


# FLEXIBLE ENGLISH DURATION INPUTS
_DURATION_ONES = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}

_DURATION_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}

_FLEX_EN_DURATION_RE = re.compile(
    r"\b("
    r"\d+|"
    r"a|an|"
    r"zero|one|two|three|four|five|six|seven|eight|nine|"
    r"ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    r"seventeen|eighteen|nineteen|"
    r"(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
    r"(?:[\s-]+(?:one|two|three|four|five|six|seven|eight|nine))?"
    r")\s*[\s-]*"
    r"(day|days|d|week|weeks|wk|wks|month|months|mo|mos)\b",
    re.I,
)

_FORTNIGHT_RE = re.compile(
    r"\b(?:a\s+|an\s+|one\s+)?fortnight\b",
    re.I,
)

# This helper converts supported English number words such as "fourteen" or
# "twenty one" into integers so written duration instructions can be handled
# using the same deterministic rules as numeric durations.
def _duration_number(
    value: str,
) -> int | None:
    token = (
        value
        .strip()
        .lower()
        .replace("-", " ")
    )

    if token.isdigit():
        return int(token)

    if token in {"a", "an"}:
        return 1

    if token in _DURATION_ONES:
        return _DURATION_ONES[token]

    if token in _DURATION_TENS:
        return _DURATION_TENS[token]

    parts = token.split()

    if (
        len(parts) == 2
        and parts[0] in _DURATION_TENS
        and parts[1] in _DURATION_ONES
    ):
        return (
            _DURATION_TENS[parts[0]]
            + _DURATION_ONES[parts[1]]
        )

    return None

# This function converts the doctor-confirmed medication duration into an end
# date. It supports common English and Urdu wording, including values such as
# "14 days", "two weeks", "a fortnight" and "two months". Unsupported wording
# returns no result instead of guessing, and the calculated end date is inclusive.
def parse_duration(
    value: str | None,
    start: date,
) -> date | None:
    """
    Parse doctor-confirmed medication duration.

    Supported English examples:
      14 days
      fourteen days
      2 weeks
      two weeks
      two-week course
      2 wk
      a week
      a fortnight
      one month
      two months

    Existing Urdu duration handling is preserved.

    The end date is inclusive.
    """

    if not value:
        return None

    text = _normalise(value)

    # A fortnight is deterministically 14 days.
    if _FORTNIGHT_RE.search(text):
        days = 14

    else:
        match = _FLEX_EN_DURATION_RE.search(
            text
        )

        if match:
            amount = _duration_number(
                match.group(1)
            )

            if amount is None:
                return None

            unit = (
                match.group(2)
                .lower()
            )

            if unit in {
                "d",
                "day",
                "days",
            }:
                days = amount

            elif unit in {
                "wk",
                "wks",
                "week",
                "weeks",
            }:
                days = amount * 7

            else:
                # Existing MediExplain deterministic
                # convention: 1 month = 30 days.
                days = amount * 30

        else:
            # Preserve the existing Urdu-duration route.
            match = AR_DURATION_RE.search(
                text
            )

            if not match:
                return None

            amount = int(
                match.group(1)
            )

            unit = match.group(2)

            if unit.startswith("دن"):
                days = amount

            elif unit.startswith("ہفت"):
                days = amount * 7

            elif unit.startswith("مہین"):
                days = amount * 30

            else:
                return None

    if days <= 0:
        return None

    return (
        start
        + timedelta(
            days=days - 1
        )
    )


# ============================================================
# DEFAULT DAILY TIMES
# ============================================================
# These are the deterministic reminder times used when the doctor specifies how
# many times per day a medicine should be taken but does not provide exact clock
# times. The same daily count therefore always produces the same reminder pattern.
DEFAULT_TIMES = {
    1: [
        time(
            9,
            0,
        )
    ],

    2: [
        time(
            9,
            0,
        ),
        time(
            21,
            0,
        ),
    ],

    3: [
        time(
            8,
            0,
        ),
        time(
            14,
            0,
        ),
        time(
            20,
            0,
        ),
    ],

    4: [
        time(
            8,
            0,
        ),
        time(
            12,
            0,
        ),
        time(
            16,
            0,
        ),
        time(
            20,
            0,
        ),
    ],
}


# ============================================================
# FREQUENCY PHRASES
# ============================================================
# These mappings recognise common doctor-confirmed daily-frequency phrases across
# English, Urdu and Punjabi Shahmukhi and convert them into a fixed number of
# reminder events per day.
ENGLISH_DAILY = {
    # Once
    "once": 1,
    "once daily": 1,
    "once a day": 1,
    "once per day": 1,
    "one time": 1,
    "one time a day": 1,
    "1x": 1,
    "1 x": 1,
    "od": 1,
    "daily": 1,

    # Twice
    "twice": 2,
    "twice daily": 2,
    "twice a day": 2,
    "twice per day": 2,
    "two times": 2,
    "two times daily": 2,
    "two times a day": 2,
    "2x": 2,
    "2 x": 2,
    "bd": 2,
    "bid": 2,

    # Three
    "three times": 3,
    "three times daily": 3,
    "three times a day": 3,
    "three times per day": 3,
    "3 times": 3,
    "3 times daily": 3,
    "3 times a day": 3,
    "3x": 3,
    "3 x": 3,
    "tid": 3,
    "tds": 3,

    # Four
    "four times": 4,
    "four times daily": 4,
    "four times a day": 4,
    "four times per day": 4,
    "4 times": 4,
    "4 times daily": 4,
    "4 times a day": 4,
    "4x": 4,
    "4 x": 4,
    "qid": 4,
}


URDU_DAILY = {
    # Once
    "دن میں ایک دفعہ": 1,
    "دن میں ایک بار": 1,
    "روز ایک دفعہ": 1,
    "روز ایک بار": 1,
    "روزانہ ایک دفعہ": 1,
    "روزانہ ایک بار": 1,

    # Twice
    "دن میں دو دفعہ": 2,
    "دن میں دو بار": 2,
    "روز دو دفعہ": 2,
    "روز دو بار": 2,
    "روزانہ دو دفعہ": 2,
    "روزانہ دو بار": 2,

    # Three
    "دن میں تین دفعہ": 3,
    "دن میں تین بار": 3,
    "روز تین دفعہ": 3,
    "روز تین بار": 3,
    "روزانہ تین دفعہ": 3,
    "روزانہ تین بار": 3,

    # Four
    "دن میں چار دفعہ": 4,
    "دن میں چار بار": 4,
    "روز چار دفعہ": 4,
    "روز چار بار": 4,
    "روزانہ چار دفعہ": 4,
    "روزانہ چار بار": 4,
}


PUNJABI_SHAHMUKHI_DAILY = {
    "دن وچ اک واری": 1,
    "روز اک واری": 1,

    "دن وچ دو واری": 2,
    "روز دو واری": 2,

    "دن وچ تین واری": 3,
    "روز تین واری": 3,

    "دن وچ چار واری": 4,
    "روز چار واری": 4,
}


# ============================================================
# FLEXIBLE ENGLISH DAILY FREQUENCY
# ============================================================
# These patterns extend the fixed phrase lists with common English variations
# such as "twice daily", "2x", "BID" and similar forms while still mapping them
# to a controlled daily reminder count.

_DAILY_COUNT_PATTERNS = {
    1: (
        re.compile(r"\bonce(?:\s*(?:daily|a\s+day|per\s+day|/\s*day))?\b", re.I),
        re.compile(r"\bone\s+time(?:\s*(?:daily|a\s+day|per\s+day|/\s*day))?\b", re.I),
        re.compile(r"\b1\s*(?:x|time)(?:s)?(?:\s*(?:daily|a\s+day|per\s+day|/\s*day))?\b", re.I),
        re.compile(r"\b(?:od|qd)\b", re.I),
    ),
    2: (
        re.compile(r"\btwice(?:\s*(?:daily|a\s+day|per\s+day|/\s*day))?\b", re.I),
        re.compile(r"\btwo\s+times(?:\s*(?:daily|a\s+day|per\s+day|/\s*day))?\b", re.I),
        re.compile(r"\b2\s*(?:x|times?)(?:\s*(?:daily|a\s+day|per\s+day|/\s*day))?\b", re.I),
        re.compile(r"\b(?:bd|bid)\b", re.I),
    ),
    3: (
        re.compile(r"\bthrice(?:\s*(?:daily|a\s+day|per\s+day|/\s*day))?\b", re.I),
        re.compile(r"\bthree\s+times(?:\s*(?:daily|a\s+day|per\s+day|/\s*day))?\b", re.I),
        re.compile(r"\b3\s*(?:x|times?)(?:\s*(?:daily|a\s+day|per\s+day|/\s*day))?\b", re.I),
        re.compile(r"\b(?:tds|tid)\b", re.I),
    ),
    4: (
        re.compile(r"\bfour\s+times(?:\s*(?:daily|a\s+day|per\s+day|/\s*day))?\b", re.I),
        re.compile(r"\b4\s*(?:x|times?)(?:\s*(?:daily|a\s+day|per\s+day|/\s*day))?\b", re.I),
        re.compile(r"\b(?:qid|qds)\b", re.I),
    ),
}

# This helper checks the flexible English frequency patterns and returns the
# recognised number of doses per day when one of the supported forms is found.
def _flexible_daily_count(text: str):
    compact = re.sub(r"[.,;:()]+", " ", text)
    compact = re.sub(r"\s+", " ", compact).strip()

    for count, patterns in _DAILY_COUNT_PATTERNS.items():
        if any(pattern.search(compact) for pattern in patterns):
            return count

    return None


# ============================================================
# EVERY-N-HOURS
# ============================================================
# These patterns recognise interval instructions such as "every 8 hours",
# abbreviated hourly wording and equivalent Urdu phrasing.
EN_EVERY_HOURS_RE = re.compile(
    r"\bevery\s+(\d{1,2})\s*(?:hours?|hrs?|h)\b",
    re.I,
)

EN_HOURLY_RE = re.compile(
    r"\b(\d{1,2})\s*(?:hourly|hrly)\b",
    re.I,
)

AR_EVERY_HOURS_RE = re.compile(
    r"ہر\s+(\d{1,2})\s*"
    r"گھنٹ(?:ہ|ے|وں)"
)

QH_RE = re.compile(
    r"\bq\s*(\d{1,2})\s*h\b",
    re.I,
)


# ============================================================
# FREQUENCY PARSER
# ============================================================
# This function interprets the doctor-confirmed medication frequency and converts
# it into one of the schedule types supported by MediExplain+: PRN, a fixed daily
# count, named times or an approved every-N-hours interval. Unsupported or
# ambiguous instructions return an explicit reason for manual scheduling instead
# of being converted into an assumed reminder pattern.

def parse_frequency(
    value: str | None,
) -> dict:

    text = _normalise(
        value
    )

    if not text:

        return {
            "supported":
                False,

            "reason":
                "Frequency is missing",
        }

    # --------------------------------------------------------
    # PRN / AS NEEDED
    # --------------------------------------------------------
# PRN/as-needed medicines are recognised separately because they must not receive
# fixed automatic reminder times.
    prn_phrases = (
        "as needed",
        "when required",
        "prn",

        "ضرورت کے مطابق",
        "ضرورت کے وقت",
        "جب ضرورت ہو",
        "ضرورت پر",

        "لوڑ پئے تے",
        "لوڑ مطابق",
    )

    if any(
        phrase == text
        or phrase in text
        for phrase
        in prn_phrases
    ):

        return {
            "supported":
                True,

            "kind":
                "prn",
        }

    # --------------------------------------------------------
    # FLEXIBLE DAILY COUNTS
    # --------------------------------------------------------

    daily_count = _flexible_daily_count(text)

    if daily_count is not None:
        return {
            "supported": True,
            "kind": "daily_count",
            "count": daily_count,
        }

    # --------------------------------------------------------
    # EXACT DAILY COUNTS
    # --------------------------------------------------------

    for mapping in (
        ENGLISH_DAILY,
        URDU_DAILY,
        PUNJABI_SHAHMUKHI_DAILY,
    ):

        if text in mapping:

            return {
                "supported":
                    True,

                "kind":
                    "daily_count",

                "count":
                    mapping[
                        text
                    ],
            }

    # Allow the known daily phrase to appear inside a longer,
    # doctor-confirmed Frequency-field value.
    for mapping in (
        URDU_DAILY,
        PUNJABI_SHAHMUKHI_DAILY,
    ):

        for phrase, count in (
            mapping.items()
        ):

            if phrase in text:

                return {
                    "supported":
                        True,

                    "kind":
                        "daily_count",

                    "count":
                        count,
                }

    # --------------------------------------------------------
    # ENGLISH FULLER WORDING
    # --------------------------------------------------------

    english_patterns = [
        (
            re.compile(
                r"\b(?:once|1\s*x|one time)"
                r"\s+(?:a|per)\s+day\b",
                re.I,
            ),
            1,
        ),
        (
            re.compile(
                r"\b(?:twice|2\s*x|two times)"
                r"\s+(?:a|per)\s+day\b",
                re.I,
            ),
            2,
        ),
        (
            re.compile(
                r"\b(?:three|3)\s+times"
                r"\s+(?:a|per)\s+day\b",
                re.I,
            ),
            3,
        ),
        (
            re.compile(
                r"\b(?:four|4)\s+times"
                r"\s+(?:a|per)\s+day\b",
                re.I,
            ),
            4,
        ),
    ]

    for pattern, count in (
        english_patterns
    ):

        if pattern.search(
            text
        ):

            return {
                "supported":
                    True,

                "kind":
                    "daily_count",

                "count":
                    count,
            }

    # --------------------------------------------------------
    # EVERY N HOURS
    # --------------------------------------------------------

    interval_match = (
        EN_EVERY_HOURS_RE.search(
            text
        )
        or EN_HOURLY_RE.search(
            text
        )
        or AR_EVERY_HOURS_RE.search(
            text
        )
        or QH_RE.search(
            text
        )
    )

    if interval_match:

        hours = int(
            interval_match.group(1)
        )

        if hours not in {
            4,
            6,
            8,
            12,
            24,
        }:

            return {
                "supported":
                    False,

                "reason":
                    (
                        f"Every {hours} hours "
                        "requires manual scheduling"
                    ),
            }

        return {
            "supported":
                True,

            "kind":
                "interval",

            "hours":
                hours,
        }

    # --------------------------------------------------------
    # NAMED TIMES
    # --------------------------------------------------------

    named = []

    named_words = (
        (
            ("morning", "صبح"),
            time(
                8,
                0,
            ),
        ),
        (
            ("afternoon", "دوپہر"),
            time(
                14,
                0,
            ),
        ),
        (
            ("evening", "شام"),
            time(
                19,
                0,
            ),
        ),
        (
            ("night", "رات"),
            time(
                21,
                0,
            ),
        ),
    )

    for words, scheduled_time in (
        named_words
    ):

        if any(
            word in text
            for word in words
        ):

            named.append(
                scheduled_time
            )

    # Remove duplicates while retaining order.
    named = list(
        dict.fromkeys(
            named
        )
    )

    if named:

        return {
            "supported":
                True,

            "kind":
                "named_times",

            "times":
                named,
        }

    return {
        "supported":
            False,

        "reason":
            (
                "Frequency could not be "
                f"parsed safely: {value}"
            ),
    }


# ============================================================
# EVENT GENERATION
# ============================================================

# This function turns the parsed medication frequency and confirmed date range
# into the actual reminder timestamps stored by the scheduler. PRN medicines
# intentionally produce no fixed events, missing or invalid durations return a
# review error, interval schedules repeat by the confirmed number of hours, and
# daily-count or named-time schedules generate events for each day in the range.

def build_events(
    frequency: str,
    start_date: date,
    end_date: date | None,
    timezone: str,
) -> tuple[
    list[datetime],
    str | None,
]:

    parsed = parse_frequency(
        frequency
    )

    if not parsed[
        "supported"
    ]:

        return (
            [],
            parsed[
                "reason"
            ],
        )

    # PRN medicines intentionally do not have fixed reminders.
    if (
        parsed[
            "kind"
        ]
        == "prn"
    ):

        return (
            [],
            None,
        )

    if end_date is None:

        return (
            [],
            (
                "Duration/end date is required "
                "for automatic reminders"
            ),
        )

    if end_date < start_date:

        return (
            [],
            "End date cannot be before start date",
        )

    # Validate timezone even though the project persists
    # local wall-clock reminder values.
    tz = ZoneInfo(
        timezone
    )

    events = []

    # --------------------------------------------------------
    # INTERVAL
    # --------------------------------------------------------

    if (
        parsed[
            "kind"
        ]
        == "interval"
    ):

        hours = (
            parsed[
                "hours"
            ]
        )

        dt = datetime.combine(
            start_date,
            time(
                8,
                0,
            ),
            tzinfo=tz,
        )

        exclusive_end = (
            datetime.combine(
                end_date
                + timedelta(
                    days=1
                ),
                time(
                    8,
                    0,
                ),
                tzinfo=tz,
            )
        )

        while (
            dt
            < exclusive_end
        ):

            events.append(
                dt.replace(
                    tzinfo=None
                )
            )

            dt += timedelta(
                hours=hours
            )

        return (
            events,
            None,
        )

    # --------------------------------------------------------
    # DAILY COUNT / NAMED TIMES
    # --------------------------------------------------------

    current = start_date

    while (
        current
        <= end_date
    ):

        if (
            parsed[
                "kind"
            ]
            == "daily_count"
        ):

            times = (
                DEFAULT_TIMES[
                    parsed[
                        "count"
                    ]
                ]
            )

        elif (
            parsed[
                "kind"
            ]
            == "named_times"
        ):

            times = (
                parsed[
                    "times"
                ]
            )

        else:

            return (
                [],
                "Unsupported schedule type",
            )

        for scheduled_time in (
            times
        ):

            events.append(
                datetime.combine(
                    current,
                    scheduled_time,
                    tzinfo=tz,
                ).replace(
                    tzinfo=None
                )
            )

        current += timedelta(
            days=1
        )

    return (
        events,
        None,
    )