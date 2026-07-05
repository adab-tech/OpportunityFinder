from app.scrapers.quality import is_low_quality_title


class TestNavigationChrome:
    def test_rejects_breadcrumb_and_nav_labels(self):
        for title in ["Breadcrumb", "Quick Links", "Mobile Navigation", "Main navigation", "Sidebar"]:
            assert is_low_quality_title(title) is True

    def test_rejects_please_wait_and_js_disabled(self):
        assert is_low_quality_title("Please wait") is True
        assert is_low_quality_title("JavaScript is disabled") is True

    def test_rejects_bare_category_labels(self):
        for title in ["Scholarship", "Scholarships", "Fellowships", "Internships", "Grants", "Jobs"]:
            assert is_low_quality_title(title) is True

    def test_rejects_browsing_and_author_lines(self):
        assert is_low_quality_title("Browsing: Africa") is True
        assert is_low_quality_title("Author: Opportunity Desk") is True

    def test_rejects_signup_prompts(self):
        assert is_low_quality_title("Sign up to receive updates for the 2026-27 school year.") is True


class TestListiclesAndRoundups:
    def test_rejects_numeric_prefixed_listicle(self):
        assert is_low_quality_title("50+ Scholarships for College Students to Apply for in 2026") is True
        assert is_low_quality_title("44 Grants, Funding and Cash Prizes Currently Open") is True

    def test_rejects_top_best_roundups(self):
        assert is_low_quality_title("Top Scholarships for Graduate Students with Upcoming Deadlines") is True
        assert is_low_quality_title("The Best PhD Scholarships with Upcoming Deadlines") is True

    def test_rejects_list_of_phrasing(self):
        assert is_low_quality_title("List of Scholarships, Eligibility and Application Links") is True

    def test_rejects_generic_job_market_roundups(self):
        assert is_low_quality_title("20 Jobs That Will Be in Demand in 2026") is True
        assert is_low_quality_title("2026 Workforce Forecast: Where the Jobs Will Be") is True
        assert is_low_quality_title("These 12 careers are your best chance to get a job in 2026") is True

    def test_rejects_recruiting_timeline_guides(self):
        assert is_low_quality_title(
            "Consulting Internships Summer 2027: The Full Application Timeline and Firm List"
        ) is True
        assert is_low_quality_title(
            "When Do Internship Applications Open? Your 2027 Timeline by Industry"
        ) is True

    def test_does_not_reject_year_prefixed_specific_program(self):
        # A 4-digit year at the start is not a listicle count.
        assert is_low_quality_title("2026 Kresge Fellowships and Snowden Emerging Artist Awards") is False


class TestPastAnnouncements:
    def test_rejects_winner_announcements_without_forward_cue(self):
        assert is_low_quality_title(
            "University of West Florida student awarded prestigious fellowship"
        ) is True
        assert is_low_quality_title("Bush Foundation announces fellowship recipients") is True

    def test_keeps_announcement_with_forward_looking_cue(self):
        # Recaps last year's winners but also links to this year's open call.
        assert is_low_quality_title(
            "Foundation announces fellowship recipients — apply now for 2027"
        ) is False


class TestOffTopicContent:
    def test_rejects_sports_content(self):
        assert is_low_quality_title(
            "Series win in Seattle shows how tricky this trade deadline will be for the Red Sox"
        ) is True
        assert is_low_quality_title("The Pirates and Rays are about to guarantee an MLB lockout") is True

    def test_rejects_gaming_content(self):
        assert is_low_quality_title("Grow a Garden Summer update 2026 patch notes") is True
        assert is_low_quality_title("Evomon Adventure Suit tier list (July 2026)") is True

    def test_rejects_local_politics_content(self):
        assert is_low_quality_title(
            "DLNR grants Waianae homeless encampment extension, drawing frustration from residents"
        ) is True
        assert is_low_quality_title("Columbiana County property tax deadline pushed back") is True
        assert is_low_quality_title("Joni Ernst is the next GOP senator on retirement watch") is True

    def test_rejects_markets_and_entertainment_content(self):
        assert is_low_quality_title("Breaking Stock Market News") is True
        assert is_low_quality_title("TV Show Book Adaptations Arriving In 2026 So Far") is True


class TestGenericInfoPages:
    def test_rejects_planning_guides_and_databases(self):
        assert is_low_quality_title("Scholarship Deadlines and Timelines: Your 2026 Planning Guide") is True
        assert is_low_quality_title("Fully Funded PhD Programs Database (2026)") is True


class TestLegitimateOpportunitiesAreKept:
    def test_keeps_well_known_named_programs_without_scholarship_vocabulary(self):
        # These are real, specific programs that never repeat scholarship/
        # grant/fellowship vocabulary in their title — relevance comes from
        # ingest context (a curated feed or targeted search), not the title.
        assert is_low_quality_title("Fulbright Foreign Student Program") is False
        assert is_low_quality_title("Erasmus Mundus Joint Masters") is False
        assert is_low_quality_title("Faculty Early Career Development Program (CAREER)") is False
        assert is_low_quality_title(
            "Google Africa Applied AI Lab 2026 for African AI Founders and Researchers"
        ) is False

    def test_keeps_named_grants_and_funds(self):
        assert is_low_quality_title(
            "Mozilla Science Mini-Grants 2018 for projects on Prototyping "
            "& Community Building ($USD 5,000 grant)"
        ) is False
        assert is_low_quality_title("Global Innovation Fund") is False
        assert is_low_quality_title("Pulitzer Center- Gender Equality Grants 2021") is False

    def test_keeps_real_job_postings_without_scholarship_vocabulary(self):
        assert is_low_quality_title(
            "Greenpeace MENA Remote Engagement Director Job Opportunity (2026): "
            "Strategic Leadership Role in Environmental Advocacy Across the MENA Region"
        ) is False
        assert is_low_quality_title("2014 Oando Graduate Trainee Program for Nigerians") is False

    def test_keeps_specific_fellowships_and_scholarships(self):
        assert is_low_quality_title("Government of Ireland Scholarship 2027 (Fully Funded)") is False
        assert is_low_quality_title("Postdoctoral Fellowships") is False


class TestEdgeCases:
    def test_rejects_empty_or_very_short_titles(self):
        assert is_low_quality_title("") is True
        assert is_low_quality_title("   ") is True
        assert is_low_quality_title("Ab") is True
        assert is_low_quality_title(None) is True
