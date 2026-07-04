from app.scrapers.synopsis import build_synopsis, extract_funding_amount


class TestExtractFundingAmount:
    def test_dollar_amount(self):
        assert extract_funding_amount("Grant worth $50,000 for researchers") == "$50,000"

    def test_up_to_phrasing(self):
        assert extract_funding_amount("Fellowship offering up to £25,000") == "up to £25,000"

    def test_no_amount_returns_none(self):
        assert extract_funding_amount("A fellowship for young leaders") is None

    def test_none_input(self):
        assert extract_funding_amount(None) is None

    def test_euro_amount(self):
        assert extract_funding_amount("Deloitte Photo Grant 2026 (up tp €25,000)") is not None


class TestBuildSynopsis:
    def test_scholarship_with_all_fields(self):
        sentence = build_synopsis(
            title="DAAD Scholarship 2026",
            opportunity_type="scholarship",
            field="STEM",
            location="Africa",
            deadline="September 23, 2026",
        )
        assert sentence.startswith("A scholarship in STEM")
        assert "Africa" in sentence
        assert "Deadline: September 23, 2026." in sentence

    def test_international_location_phrased_differently(self):
        sentence = build_synopsis(
            title="Global Fellowship",
            opportunity_type="fellowship",
            location="International",
        )
        assert "open internationally" in sentence
        assert "open to applicants in International" not in sentence

    def test_rolling_deadline_phrasing(self):
        sentence = build_synopsis(
            title="Ongoing Grant",
            opportunity_type="grant",
            deadline="Rolling",
        )
        assert "rolling basis" in sentence
        assert "Deadline: Rolling" not in sentence

    def test_no_deadline_omits_deadline_sentence(self):
        sentence = build_synopsis(title="Job", opportunity_type="job")
        assert "Deadline" not in sentence

    def test_funding_amount_included_when_present(self):
        sentence = build_synopsis(
            title="Research Grant worth $10,000",
            opportunity_type="grant",
        )
        assert "$10,000" in sentence

    def test_unknown_type_falls_back_to_generic(self):
        sentence = build_synopsis(title="Something", opportunity_type="mystery")
        assert sentence.startswith("An opportunity")

    def test_result_is_a_single_reasonable_sentence(self):
        sentence = build_synopsis(
            title="Test",
            opportunity_type="scholarship",
            field="Law",
            location="Kenya",
            deadline="1 May 2026",
        )
        assert sentence.count(".") >= 1
        assert len(sentence) < 300
