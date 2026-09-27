import unittest
from datetime import date

from app.services.scheduler import parse_duration, parse_frequency, build_events
# These unit tests check the deterministic medication scheduler against common
# prescription instructions and safety boundaries. They verify expected reminder
# counts for supported frequencies and durations, confirm that PRN instructions
# do not create fixed reminders, and make sure missing or unsupported scheduling
# information is not guessed and is instead left for review.

class SchedulerTests(unittest.TestCase):
    def test_twice_daily_seven_days_is_fourteen(self):
        start = date(2026, 8, 10)
        end = parse_duration("7 days", start)
        events, error = build_events("twice a day", start, end, "Asia/Karachi")
        self.assertIsNone(error)
        self.assertEqual(len(events), 14)

    def test_three_times_daily_five_days_is_fifteen(self):
        start = date(2026, 8, 10)
        end = parse_duration("5 days", start)
        events, error = build_events("three times a day", start, end, "Asia/Karachi")
        self.assertIsNone(error)
        self.assertEqual(len(events), 15)

    def test_missing_duration_never_invents_schedule(self):
        events, error = build_events("twice daily", date(2026, 8, 10), None, "Asia/Karachi")
        self.assertEqual(events, [])
        self.assertIn("Duration", error)

    def test_prn_has_no_fixed_events(self):
        events, error = build_events("as needed", date(2026, 8, 10), None, "Asia/Karachi")
        self.assertEqual(events, [])
        self.assertIsNone(error)

    def test_unsupported_interval_requires_review(self):
        parsed = parse_frequency("every 5 hours")
        self.assertFalse(parsed["supported"])

    def test_named_morning_and_night(self):
        start = date(2026, 8, 10)
        events, error = build_events("morning and night", start, start, "Asia/Karachi")
        self.assertIsNone(error)
        self.assertEqual(len(events), 2)


if __name__ == "__main__":
    unittest.main()
