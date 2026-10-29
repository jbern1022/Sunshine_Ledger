from app.models import Entity
from app.pipeline.title_cleanup import clean_stored_titles

DIRTY = "ORD Rezoning at 0 Pritchard Rd\r\n8/25/26 CO Introduced: LUZ \r\n(Small-Scale 2026-655)"


def _bill(db, name, key="legistar_matter_id"):
    e = Entity(entity_type="bill", name=name, jurisdiction_level="city", jurisdiction_name="Jacksonville",
               external_ids={key: 1}, attributes={})
    db.add(e)
    db.flush()
    return e


def test_dry_run_counts_but_changes_nothing(db_session):
    e = _bill(db_session, DIRTY)
    changed = clean_stored_titles(db_session, apply=False)
    assert changed == 1
    assert e.name == DIRTY


def test_apply_flattens_line_breaks_and_drops_the_history_line(db_session):
    e = _bill(db_session, DIRTY)
    assert clean_stored_titles(db_session, apply=True) == 1
    assert e.name == "ORD Rezoning at 0 Pritchard Rd (Small-Scale 2026-655)"
    assert clean_stored_titles(db_session, apply=True) == 0


def test_state_bills_and_clean_titles_are_left_alone(db_session):
    state = _bill(db_session, "HB 1\nline two", key="legiscan_id")
    clean = _bill(db_session, "Already clean title")
    assert clean_stored_titles(db_session, apply=True) == 0
    assert state.name == "HB 1\nline two"
    assert clean.name == "Already clean title"
