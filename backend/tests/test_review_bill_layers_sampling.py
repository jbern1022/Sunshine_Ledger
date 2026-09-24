"""Tests for review_bill_layers' --bills-from parsing and sample combination.

--bills-from lets a second model run cover exactly the same bills an
earlier report ran, so the two are comparable; --sample N on top of it
draws N *additional* random bills, excluding the ones already listed.
"""

import argparse

from app import config as config_module
from app.pipeline.review_bill_layers import _sample, build_client, parse_bills_from_report

REPORT = """# Bill layers quality review (llama3.1:8b)

- Bill Says quotes verified: 10/12

## H0565 — Genetic Testing Nondiscrimination

#### Bill Says · bill text
- state: `verified`

## S1502 — Some Other Bill

#### Bill Says · bill text
- state: `verified`

## 2026-0548-W — A Local Ordinance

#### Bill Says · bill text
- state: `verified`
"""


def test_parse_bills_from_report_extracts_numbers_in_order():
    assert parse_bills_from_report(REPORT) == ["H0565", "S1502", "2026-0548-W"]


def test_parse_bills_from_report_ignores_non_heading_lines():
    assert parse_bills_from_report("no headings here\njust prose") == []


def test_sample_with_explicit_bill_numbers_preserves_requested_order(db_session, bill_factory):
    bill_factory(bill_number="S1502", name="Second")
    bill_factory(bill_number="H0565", name="First")

    entities = _sample(db_session, 0, ["H0565", "S1502"])

    assert [e.bill.bill_number for e in entities] == ["H0565", "S1502"]


def test_sample_skips_unknown_bill_numbers(db_session, bill_factory):
    bill_factory(bill_number="H0565", name="First")

    entities = _sample(db_session, 0, ["H0565", "S9999"])

    assert [e.bill.bill_number for e in entities] == ["H0565"]


def test_build_client_defaults_to_layers_model_and_300s_timeout(monkeypatch):
    monkeypatch.setattr(config_module.settings, "ollama_layers_model", "qwen2.5:14b")
    args = argparse.Namespace(model=None)

    client = build_client(args)

    assert client.model == "qwen2.5:14b"
    assert client._client.timeout.read == 300


def test_build_client_model_flag_overrides_layers_model(monkeypatch):
    monkeypatch.setattr(config_module.settings, "ollama_layers_model", "qwen2.5:14b")
    args = argparse.Namespace(model="llama3.1:8b")

    client = build_client(args)

    assert client.model == "llama3.1:8b"
    assert client._client.timeout.read == 300


def test_sample_exclude_omits_listed_bills_from_random_draw(db_session, bill_factory):
    excluded = bill_factory(bill_number="H0565", name="Excluded", status="Introduced")
    excluded.bill.full_text = "Section 1. Something else."
    kept = bill_factory(bill_number="H0999", name="Kept", status="Introduced")
    kept.bill.full_text = "Section 1. Something."
    db_session.commit()

    entities = _sample(db_session, 20, [], exclude=["H0565"])

    numbers = [e.bill.bill_number for e in entities]
    assert "H0565" not in numbers
    assert "H0999" in numbers
