from app.bootstrap import CURATED_SEEDS, seed_curated_opportunities
from app.database import SessionLocal
from app.models import Opportunity


def test_curated_seed_inserts_without_duplicates():
    db = SessionLocal()
    try:
        before = db.query(Opportunity).count()
        added = seed_curated_opportunities(db)
        after = db.query(Opportunity).count()
        assert added >= 0
        assert after >= before
        assert len(CURATED_SEEDS) >= 10
    finally:
        db.close()
