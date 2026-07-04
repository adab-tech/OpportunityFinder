from app.scrapers.keywords import detect_opportunity_type


class TestDetectOpportunityType:
    def test_scholarship(self):
        assert detect_opportunity_type("Fully Funded Scholarship for African Students") == "scholarship"

    def test_fellowship(self):
        assert detect_opportunity_type("2026 Research Fellowship Program Now Open") == "fellowship"

    def test_grant(self):
        assert detect_opportunity_type("Small Grant: Call for Proposals") == "grant"

    def test_job(self):
        assert detect_opportunity_type("Communications Officer (Remote) Vacancy") == "job"

    def test_internship_classified_as_job(self):
        assert detect_opportunity_type("Paid Internship at a Global NGO") == "job"

    def test_unmatched_falls_back_to_default(self):
        assert detect_opportunity_type("A Completely Unrelated Announcement") == "other"

    def test_custom_default(self):
        assert detect_opportunity_type("Nothing relevant here", default="job") == "job"

    def test_case_insensitive(self):
        assert detect_opportunity_type("SCHOLARSHIP OPPORTUNITY") == "scholarship"

    def test_scholarship_checked_before_job_keywords(self):
        # "position" style job keywords shouldn't shadow an explicit scholarship title
        assert detect_opportunity_type("Scholarship Program Officer Announcement") == "scholarship"
