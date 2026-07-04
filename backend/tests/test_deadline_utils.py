from app.scrapers.deadline_utils import extract_deadline


class TestExtractDeadline:
    def test_none_or_empty_returns_none(self):
        assert extract_deadline("") is None
        assert extract_deadline(None) is None

    def test_ordinal_suffix_previously_unmatched(self):
        # Real DAAD listing text — this exact case was returning None
        # before the fix because "23rd" broke the digit-only pattern.
        text = "Application Deadline: September 23rd, 2026 Applications are now open..."
        assert extract_deadline(text) == "September 23rd, 2026"

    def test_day_month_year_order(self):
        text = "Application Deadline: 29 June 2026 (4:00 PM) Applications are now open..."
        assert extract_deadline(text) == "29 June 2026"

    def test_varying_deadline_falls_back_to_rolling(self):
        text = "Application Deadline: varying by country. Applications are open."
        assert extract_deadline(text) == "Rolling"

    def test_plain_labelled_deadline_no_ordinal(self):
        text = "deadline: October 15, 2026 for all applicants"
        assert extract_deadline(text) == "October 15, 2026"

    def test_closing_date_phrasing(self):
        text = "Closing date: 1 May 2026 for early submissions"
        assert extract_deadline(text) == "1 May 2026"

    def test_iso_date_fallback(self):
        text = "Key dates: 2026-09-01 is when the program starts"
        assert extract_deadline(text) == "2026-09-01"

    def test_rolling_admission_phrase(self):
        text = "This fellowship accepts applications on a rolling basis year-round."
        assert extract_deadline(text) == "Rolling"

    def test_no_date_or_rolling_signal_returns_none(self):
        text = "This is a wonderful opportunity for young professionals."
        assert extract_deadline(text) is None

    def test_labelled_deadline_wins_over_rolling_mention(self):
        # A listing might mention "rolling" for something else (e.g. rolling
        # admissions to a mailing list) but state a concrete deadline — the
        # concrete date should win.
        text = "Newsletter signup is rolling. Application Deadline: 1 May 2026."
        assert extract_deadline(text) == "1 May 2026"

    def test_slash_date_format(self):
        text = "Deadline: 12/31/2026 for all regions"
        assert extract_deadline(text) == "12/31/2026"
