from app.federal.earmark_tables import parse_page, split_requestor


def W(text, x0, top):
    return {"text": text, "x0": x0, "x1": x0 + 5 * len(text), "top": top}


def line(top, left, amounts, state, req):
    out = [W(t, 101 + 8 * i, top) for i, t in enumerate(left)]
    out += [W(a, 435 + 50 * i, top) for i, a in enumerate(amounts)]
    if state:
        out.append(W(state, 582, top))
    out += [W(r, 599 + 6 * i, top) for i, r in enumerate(req)]
    return out


def test_a_row_with_a_wrapped_project_name_and_requestors():
    words = (
        line(148, ["Army", "Corps", "Construction", "Florida", "Keys", "Water", "FL;", "U.S.", "Army"], ["............................", "4,333,000", "4,333,000"], "FL", ["Gimenez"])
        + [W("Engineers", 257, 156)]
        + line(173, ["Army", "Corps", "Construction", "Upper", "Mississippi", "IL;", "U.S.", "Army"], ["............................", "250,000,000", "250,000,000"], "IL", ["Budzinski,", "Graves", "(MO),"])
        + [W("Sorensen", 599, 181), W("Engineers", 257, 181)]
    )
    rows = parse_page(words)
    assert len(rows) == 2
    a, b = rows
    assert a.state == "FL" and a.amount == 4333000 and a.requestors == ("Gimenez",)
    assert a.project.endswith("Engineers") and a.recipient == "U.S. Army Engineers"
    assert b.state == "IL" and b.amount == 250000000 and b.requestors == ("Budzinski", "Graves (MO)", "Sorensen")


def test_the_additional_amount_is_the_second_to_last_of_three():
    words = line(100, ["Agency", "Acct", "Thing;", "Recipient"], ["$11,600,000", "$1,200,000", "$12,800,000"], "AK", ["Begich"])
    assert parse_page(words)[0].amount == 1200000
    two = line(100, ["Agency", "Acct", "Thing;", "Recipient"], ["2,000,000", "2,000,000"], "FL", ["Soto"])
    assert parse_page(two)[0].amount == 2000000


def test_header_and_noise_lines_do_not_start_rows():
    noise = [W("ENERGY", 300, 40), W("239", 659, 298)] + line(60, ["Agency", "Account", "Project", "Name;", "Recipient"], [], None, [])
    assert parse_page(noise) == []


def test_split_requestor():
    assert split_requestor("Kelly (IL)") == ("Kelly", "IL")
    assert split_requestor("Gimenez") == ("Gimenez", None)
