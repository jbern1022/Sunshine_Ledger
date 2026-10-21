from app.impact_lens.tally import format_report, parse_sheet

SHEET = """# Impact Lens criteria: hand-labeling sheet

## H1389 (2026 Regular Session), who_it_affects v2

### Entry 0: Landlords
- **Change:** x
- **Audience:** role in ['landlord']
- **Review tier:** simple
- **Verdict:** correct
- **Note:**

### Entry 1: Developers
- **Audience:** role in ['property developer']
- **Verdict:** `wrong` - a date was mapped as a property type
- **Note:** condition 0 is a date, not a property type

### Entry 2: Counties
- **Verdict:** Missed
- **Note:**

### Entry 3: Anyone
- **Not mapped yet.**

### Entry 4: Renters
- **Verdict:**
- **Note:**

## S1166 (2026 Regular Session), who_it_affects v1

### Entry 0: Insurers
- **Verdict:** unsure
- **Note:** hard to say

### Entry 1: Insured
- **Verdict:** perhaps
- **Note:**
"""


def test_parse_reads_verdicts_notes_and_unmapped_entries():
    t = parse_sheet(SHEET)
    assert [(e.bill.split(" (")[0], e.index, e.verdict, e.mapped) for e in t.entries] == [
        ("H1389", 0, "correct", True),
        ("H1389", 1, "wrong", True),
        ("H1389", 2, "missed", True),
        ("H1389", 3, "", False),
        ("H1389", 4, "", True),
        ("S1166", 0, "unsure", True),
        ("S1166", 1, "perhaps", True),
    ]
    assert t.entries[1].note == "condition 0 is a date, not a property type"


def test_counts_separate_unlabeled_unmapped_and_unrecognized():
    counts = parse_sheet(SHEET).counts()
    assert counts["correct"] == 1 and counts["wrong"] == 1 and counts["missed"] == 1 and counts["unsure"] == 1
    assert counts["no verdict yet"] == 1 and counts["not mapped"] == 1 and counts["unrecognized"] == 1


def test_report_gives_the_wrong_rate_and_lists_each_wrong_entry():
    report = format_report("sheet.md", parse_sheet(SHEET))
    assert "wrong-mapping rate: 1 of 4 labeled (25%)" in report
    assert "WRONG  H1389 (2026 Regular Session), who_it_affects v2 entry 1 (Developers): condition 0 is a date" in report


def test_an_empty_or_unlabeled_sheet_has_no_rate():
    report = format_report("blank.md", parse_sheet("## H1 (2026), who_it_affects v1\n\n### Entry 0: X\n- **Verdict:** \n- **Note:** \n"))
    assert "no verdict yet: 1" in report and "rate" not in report
