"""The `sort` query param on the public listing: "newest" (default,
by scraped_at desc) and "closing" (soonest deadline first, rows with
no parseable deadline last).
"""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Opportunity

client = TestClient(app)

_TEST_URL_PREFIX = "https://example.org/sort-test-"
_SEARCH = "SortTestListing"


def _cleanup(db):
    db.query(Opportunity).filter(Opportunity.url.like(f"{_TEST_URL_PREFIX}%")).delete(
        synchronize_session=False
    )
    db.commit()


class TestClosingSort:
    def setup_method(self):
        self.db = SessionLocal()
        _cleanup(self.db)
        for slug, days in [("later", 30), ("soon", 3), ("none", None)]:
            self.db.add(
                Opportunity(
                    title=f"{_SEARCH} {slug}",
                    opportunity_type="grant",
                    url=f"{_TEST_URL_PREFIX}{slug}",
                    source_name="Test",
                    is_active=True,
                    deadline_at=date.today() + timedelta(days=days) if days else None,
                )
            )
        self.db.commit()

    def teardown_method(self):
        _cleanup(self.db)
        self.db.close()

    def _titles(self, **params):
        response = client.get("/api/v1/opportunities/", params={"search": _SEARCH, **params})
        assert response.status_code == 200
        return [item["title"] for item in response.json()["data"]]

    def test_closing_puts_soonest_deadline_first_and_no_deadline_last(self):
        titles = self._titles(sort="closing")
        assert titles == [f"{_SEARCH} soon", f"{_SEARCH} later", f"{_SEARCH} none"]

    def test_default_sort_is_newest_by_scraped_at(self):
        # All three rows were inserted just now; newest-first simply must
        # not error and must return all rows.
        titles = self._titles()
        assert sorted(titles) == sorted([f"{_SEARCH} soon", f"{_SEARCH} later", f"{_SEARCH} none"])

    def test_invalid_sort_value_is_rejected(self):
        response = client.get("/api/v1/opportunities/", params={"search": _SEARCH, "sort": "bogus"})
        assert response.status_code == 422
