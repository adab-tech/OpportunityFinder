from datetime import date

from app.scrapers.expiry import extract_years, is_expired, is_stale_by_title


class TestExtractYears:
    def test_no_year_returns_empty(self):
        assert extract_years("KKR Small Business Builders") == []

    def test_single_year(self):
        assert extract_years("Pulitzer Center Gender Equality Grants 2021") == [2021]

    def test_multiple_years(self):
        assert extract_years("2027/2028 Atlantic Fellows for Equity in Brain Health") == [2027, 2028]

    def test_year_embedded_mid_sentence(self):
        title = "International Monetary Fund Internship Program (FIP) 2021 for professionals"
        assert extract_years(title) == [2021]


class TestIsStaleByTitle:
    def test_no_year_is_never_stale(self):
        # Can't confirm expiry without a signal — must not guess.
        assert is_stale_by_title("KKR Small Business Builders", reference_year=2026) is False

    def test_past_year_is_stale(self):
        title = "Total E&P Nigeria CPFA Limited Recruitment 2019"
        assert is_stale_by_title(title, reference_year=2026) is True

    def test_current_year_is_not_stale(self):
        assert is_stale_by_title("DAAD Scholarship 2026", reference_year=2026) is False

    def test_future_year_is_not_stale(self):
        assert is_stale_by_title("DAAD Scholarship 2027", reference_year=2026) is False

    def test_uses_most_recent_year_when_multiple_present(self):
        # A program mentioning both a past founding year and an upcoming
        # cohort year should be judged by the more recent (relevant) one.
        assert is_stale_by_title("Since 1975 — 2027/2028 Fellows Program", reference_year=2026) is False

    def test_all_past_years_is_stale(self):
        assert is_stale_by_title("The 2019/2020 Recruitment Cycle", reference_year=2026) is True


class TestIsExpired:
    def test_past_deadline_at_is_expired(self):
        assert is_expired(date(2024, 5, 21), "Canon/Visa pour l'Image Photojournalist Grant") is True

    def test_future_deadline_at_is_not_expired(self):
        assert is_expired(date(2027, 5, 21), "Some Future Grant") is False

    def test_deadline_at_today_is_not_expired(self):
        today = date(2026, 7, 5)
        assert is_expired(today, "Deadline Today Grant", reference_date=today) is False

    def test_no_deadline_falls_back_to_title_year(self):
        assert is_expired(None, "IMF Internship Program (FIP) 2021", reference_date=date(2026, 1, 1)) is True

    def test_no_deadline_no_year_is_not_expired(self):
        assert is_expired(None, "KKR Small Business Builders", reference_date=date(2026, 1, 1)) is False

    def test_deadline_at_takes_priority_over_title_year(self):
        # Even if the title happens to mention an old year, a future
        # parsed deadline is the more trustworthy, definitive signal.
        result = is_expired(
            date(2027, 1, 1), "2019 Legacy Program, Reopened for 2027", reference_date=date(2026, 1, 1)
        )
        assert result is False
