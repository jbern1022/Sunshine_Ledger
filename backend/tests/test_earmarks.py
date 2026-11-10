from datetime import date

import pytest

from app.federal import earmarks as em
from app.models import Entity, FederalEarmark, OfficeTenure

HEADER = ["Member Lastname", "Member Firstname", "District", "Party", "Subcommittee", "Recipient", "Project Description",
          "Recipient Address", "Amount Requested", "Member URL"]


def rows():
    return [
        {"member_last": "Moskowitz", "member_first": "Jared", "district": "FL23", "party": "D", "subcommittee": "Transportation",
         "recipient": "City of Sunrise", "description": "Drainage upgrade", "recipient_address": "1 Main St,Sunrise,Florida,33313",
         "amount": 1500000, "member_url": "https://example.house.gov/cpf"},
        {"member_last": "Adams", "district": "NC12", "subcommittee": "CJS", "recipient": "Elon", "description": "x", "amount": 5},
        {"member_last": "Fine", "district": "FL6", "subcommittee": "CJS", "recipient": "", "description": "no recipient"},
    ]


def person(db, name, district):
    p = Entity(entity_type="person", name=name)
    db.add(p)
    db.flush()
    db.add(OfficeTenure(person_entity_id=p.id, office_type="us_house", state="FL", district=district, start_date=date(2025, 1, 3), source="test"))
    db.commit()
    return p


def test_florida_district_parsing():
    assert em.florida_district("FL12") == "CD-012" and em.florida_district("fl-6") == "CD-006"
    for bad in ("NC12", "FL0", "FL29", "", None, "FL"):
        assert em.florida_district(bad) is None


def test_import_keeps_only_florida_rows_links_by_seat_and_name_and_is_idempotent(db_session):
    p = person(db_session, "Jared Moskowitz", 23)
    stats = em.import_rows(db_session, rows(), fiscal_year=2027, stage="requested", source_url="https://x/y.xlsx")
    assert stats == {"seen": 3, "florida": 2, "new": 1, "existing": 0, "linked": 1, "skipped": 1}
    e = db_session.query(FederalEarmark).one()
    assert e.district == "CD-023" and e.amount == 1500000 and e.person_entity_id == p.id and e.stage == "requested"
    again = em.import_rows(db_session, rows(), fiscal_year=2027, stage="requested", source_url="https://x/y.xlsx")
    assert again["new"] == 0 and again["existing"] == 1 and db_session.query(FederalEarmark).count() == 1
    em.import_rows(db_session, rows(), fiscal_year=2027, stage="included", source_url="https://x/z.pdf")
    assert db_session.query(FederalEarmark).count() == 2  # the same project at another stage is a separate row


def test_a_name_without_the_seat_or_an_ambiguous_match_is_not_linked(db_session):
    person(db_session, "Jared Moskowitz", 22)  # right name, wrong seat
    em.import_rows(db_session, rows()[:1], fiscal_year=2027, stage="requested", source_url="u")
    assert db_session.query(FederalEarmark).one().person_entity_id is None
    person(db_session, "Jared Moskowitz", 23)
    person(db_session, "Jane Moskowitz", 23)
    db_session.query(FederalEarmark).delete()
    db_session.commit()
    em.import_rows(db_session, rows()[:1], fiscal_year=2027, stage="requested", source_url="u")
    assert db_session.query(FederalEarmark).one().person_entity_id is None  # two candidates: refuse to guess


def test_read_rows_from_csv_and_missing_columns(tmp_path):
    f = tmp_path / "t.csv"
    f.write_text(",".join(HEADER) + "\nMoskowitz,Jared,FL23,D,Transportation,City of Sunrise,Drainage,1 Main,\"$1,500,000\",http://u\n")
    r = em.read_rows(f)
    assert r[0]["member_last"] == "Moskowitz" and em._amount(r[0]["amount"]) == 1500000
    g = tmp_path / "bad.csv"
    g.write_text("Member Lastname,District\nA,FL1\n")
    with pytest.raises(em.EarmarkImportError):
        em.read_rows(g)


def test_read_rows_from_xlsx(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADER + [None])
    ws.append(["Moskowitz", "Jared", "FL23", "D", "Transportation", "City of Sunrise", "Drainage", "1 Main", 1500000, "http://u", None])
    f = tmp_path / "t.xlsx"
    wb.save(f)
    assert em.read_rows(f)[0]["recipient"] == "City of Sunrise"


def test_api_labels_the_stage_and_filters(client, db_session):
    p = person(db_session, "Jared Moskowitz", 23)
    em.import_rows(db_session, rows()[:1], fiscal_year=2027, stage="requested", source_url="https://x/y.xlsx")
    body = client.get("/earmarks?district=CD-023").json()
    assert body["total"] == 1 and "Senate" in body["note"]
    item = body["items"][0]
    assert item["stage"] == "requested" and item["stage_label"].startswith("A member's request. Not funding")
    assert item["member"] == "Jared Moskowitz" and item["person_id"] == str(p.id)
    assert client.get(f"/earmarks?person_id={p.id}").json()["total"] == 1
    assert client.get("/earmarks?district=CD-001").json()["total"] == 0
    assert client.get("/earmarks?stage=enacted").json()["total"] == 0
    assert client.get("/earmarks?district=bad").status_code == 422


def test_table_rows_attribute_only_unique_florida_requestors(db_session):
    from app.federal.earmark_tables import TableRow

    gim = person(db_session, "Carlos Gimenez", 28)
    soto = person(db_session, "Darren Soto", 9)
    rows = [
        TableRow("Army Corps Construction Florida Keys Water; U.S. Army Corps of Engineers", "U.S. Army Corps of Engineers", 4333000, "FL", ("Gimenez",)),
        TableRow("Army Corps Cook County, IL; U.S. Army Corps", "U.S. Army Corps", 2000000, "IL", ("Kelly (IL)", "Soto (VA)")),  # other states: none
        TableRow("Shingle Creek, FL; U.S. Army Corps", "U.S. Army Corps", 600000, "FL", ("Soto", "Budzinski")),
    ]
    s = em.import_table_rows(db_session, rows, fiscal_year=2027, stage="included", subcommittee="Energy and Water Development", source_url="https://x/ew.pdf")
    assert s["new"] == 2 and s["florida_requestors"] == 2
    got = {(e.member_last, e.district, e.amount, e.stage, e.person_entity_id) for e in db_session.query(FederalEarmark)}
    assert got == {("Gimenez", "CD-028", 4333000, "included", gim.id), ("Soto", "CD-009", 600000, "included", soto.id)}
    again = em.import_table_rows(db_session, rows, fiscal_year=2027, stage="included", subcommittee="Energy and Water Development", source_url="https://x/ew.pdf")
    assert again["new"] == 0 and again["existing"] == 2


def test_two_florida_members_with_one_surname_are_not_guessed(db_session):
    from app.federal.earmark_tables import TableRow

    person(db_session, "Brian Scott", 3)
    person(db_session, "Rick Scott", 4)
    s = em.import_table_rows(db_session, [TableRow("P; R", "R", 1, "FL", ("Scott",))], fiscal_year=2027, stage="included", subcommittee="X", source_url="u")
    assert s["new"] == 0 and s["ambiguous"] == 1
    s = em.import_table_rows(db_session, [TableRow("P; R", "R", 1, "FL", ("Scott (FL)",))], fiscal_year=2027, stage="included", subcommittee="X", source_url="u")
    assert s["ambiguous"] == 1  # the state suffix alone does not separate two Florida members; still refused


def test_consolidated_awards_workbook_rows(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Appropriations Bill", "Agency", "Account", "State/Location", "Project", "Location/Recipient", "House Amount", "House Requestor(s)", "Party"])
    ws.append(["Energy and Water", "Corps", "Construction", "Key West, FL", "Florida  Keys  Water", "Monroe County", 4333000, "Gimenez, Kelly (IL)", "R"])
    ws.append(["Agriculture", "ARS", "B&F", "Lincoln, NE", "Lab", "U of Nebraska", 5000000, "Flood", "R"])
    ws.append(["Agriculture", "ARS", "B&F", "X, NC", "no requestor", "R", 1, None, None])
    f = tmp_path / "awards.xlsx"
    wb.save(f)
    rows = em.read_award_rows(f)
    assert len(rows) == 2 and rows[0].requestors == ("Gimenez", "Kelly (IL)") and rows[0].project == "Florida Keys Water"
    assert rows[0].state == "FL" and rows[0].amount == 4333000 and rows[0].subcommittee == "Energy and Water"
    bad = tmp_path / "bad.xlsx"
    wb2 = openpyxl.Workbook()
    wb2.active.append(["a", "b"])
    wb2.save(bad)
    with pytest.raises(em.EarmarkImportError):
        em.read_award_rows(bad)


def test_awards_import_uses_the_rows_own_subcommittee(db_session):
    from app.federal.earmark_tables import TableRow

    person(db_session, "Carlos Gimenez", 28)
    em.import_table_rows(db_session, [TableRow("Florida Keys Water", "Monroe County", 4333000, "FL", ("Gimenez",), "Energy and Water")],
                         fiscal_year=2027, stage="included", subcommittee="", source_url="u")
    assert db_session.query(FederalEarmark).one().subcommittee == "Energy and Water"
