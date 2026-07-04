from datetime import UTC, datetime

from app.scrapers.keywords import OPPORTUNITY_KEYWORD_TEMPLATES, build_google_queries


class TestBuildGoogleQueries:
    def test_queries_include_current_and_next_year(self):
        current_year = datetime.now(UTC).year
        next_year = current_year + 1
        queries = build_google_queries("scholarship")

        assert any(str(current_year) in q for q in queries)
        assert any(str(next_year) in q for q in queries)

    def test_no_hardcoded_year_leaks_into_output(self):
        # Regression guard: templates must use {year}, never a literal year
        # baked in, or queries silently go stale after that year passes.
        for templates in OPPORTUNITY_KEYWORD_TEMPLATES.values():
            for template in templates:
                assert "{year}" in template

    def test_query_count_doubles_for_two_years(self):
        templates = OPPORTUNITY_KEYWORD_TEMPLATES["job"]
        queries = build_google_queries("job")
        assert len(queries) == len(templates) * 2

    def test_extra_keywords_appended(self):
        queries = build_google_queries("grant", extra_keywords=["renewable energy"])
        assert any("renewable energy" in q for q in queries)

    def test_unknown_type_returns_only_extra_keywords(self):
        queries = build_google_queries("not-a-real-type", extra_keywords=["x"])
        assert queries == ['"not-a-real-type" "x" "apply"']
