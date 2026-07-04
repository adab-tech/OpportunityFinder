from app.scrapers.synopsis import build_synopsis, extract_funding_amount, extract_meaningful_sentence


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


class TestExtractMeaningfulSentence:
    def test_none_or_empty_returns_none(self):
        assert extract_meaningful_sentence(None) is None
        assert extract_meaningful_sentence("") is None

    def test_skips_leading_deadline_and_boilerplate_opener(self):
        # Real DAAD listing text — this exact case was producing a
        # generic restated-fields sentence before the rewrite.
        text = (
            "Application Deadline: September 23rd, 2026 Applications are now open "
            "for the 2026/2027 Heinrich Böll Foundation Scholarships. The Heinrich "
            "Böll Foundation offers prestigious scholarship opportunities for highly "
            "motivated international students."
        )
        result = extract_meaningful_sentence(text)
        assert result is not None
        assert result.startswith("The Heinrich")
        assert "Application Deadline" not in result
        assert "Applications are now open" not in result

    def test_strips_wordpress_footer(self):
        text = (
            "The Horizon Institute for Public Service has launched applications for "
            "the AI Rapid Response Fellowship 2026, a one-year opportunity for "
            "AI, cybersecurity, and policy professionals. "
            "The post AI Rapid Response Fellowship 2026 appeared first on Opportunities for Youth ."
        )
        result = extract_meaningful_sentence(text)
        assert "appeared first on" not in result
        assert result.startswith("The Horizon Institute")

    def test_all_boilerplate_returns_none(self):
        text = "Application Deadline: 1 May 2026. Applications are now open for this program."
        assert extract_meaningful_sentence(text) is None

    def test_skips_nsf_style_deadline_phrasing(self):
        # Real NSF listing text, already run through _plain_text's <br />
        # -> ". " conversion (see test_rss_ingest.py for the raw-HTML
        # version of this same regression).
        text = (
            "Letter of Intent Deadline Date: July 9, 2026. Program Guidelines: NSF 23-598. "
            "The Historically Black Colleges and Universities Excellence in Research program "
            "supports research capacity building at HBCUs through targeted funding."
        )
        result = extract_meaningful_sentence(text)
        assert result is not None
        assert result.startswith("The Historically Black")

    def test_does_not_split_on_us_abbreviation(self):
        # Real NSF listing text — "U.S." was being treated as a sentence
        # end, truncating the synopsis to a near-empty fragment.
        text = (
            "The National Science Foundation invites investigators at U.S. "
            "institutions to submit proposals for Arctic research opportunities."
        )
        result = extract_meaningful_sentence(text)
        assert result is not None
        assert "U.S. institutions" in result

    def test_short_fragments_are_skipped(self):
        text = (
            "Apply now. Short. "
            "This is a properly substantive sentence describing the actual program in detail."
        )
        result = extract_meaningful_sentence(text)
        assert result.startswith("This is a properly substantive")

    def test_long_sentence_is_truncated(self):
        text = (
            "This is a very long sentence that goes on and on "
            + ("and on " * 30)
            + "describing everything."
        )
        result = extract_meaningful_sentence(text, max_length=100)
        assert len(result) <= 101  # allow the trailing ellipsis char
        assert result.endswith("…")


class TestBuildSynopsis:
    def test_prefers_real_description_over_generic_template(self):
        description = (
            "The Heinrich Böll Foundation offers prestigious scholarship opportunities "
            "for highly motivated international students pursuing graduate study."
        )
        sentence = build_synopsis(
            title="Heinrich Böll Scholarship",
            opportunity_type="scholarship",
            field="STEM",
            location="Africa",
            deadline="September 23, 2026",
            description=description,
        )
        assert sentence.startswith("The Heinrich Böll Foundation")
        # Must not fall back to the generic restated-fields sentence when
        # real description text is available.
        assert "open to applicants in Africa" not in sentence

    def test_never_restates_deadline_in_generic_fallback(self):
        sentence = build_synopsis(
            title="Bare Listing With No Description",
            opportunity_type="grant",
            deadline="19 January 2018",
        )
        assert "Deadline" not in sentence
        assert "2018" not in sentence

    def test_international_location_phrased_differently(self):
        sentence = build_synopsis(
            title="Global Fellowship",
            opportunity_type="fellowship",
            location="International",
        )
        assert "open internationally" in sentence
        assert "open to applicants in International" not in sentence

    def test_funding_amount_included_in_fallback_when_present(self):
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
