from datetime import date

import pytest

from brighton.transform.teams import canonical_team, team_id
from brighton.transform.utils import classify_fee_gbp, normalize_name, parse_date, parse_money


@pytest.mark.parametrize(
    "text,expected",
    [
        ("£52,000,000", (52_000_000, "GBP")),
        ("£6.5m", (6_500_000, "GBP")),
        ("£30 million", (30_000_000, "GBP")),
        ("£900,000", (900_000, "GBP")),
        ("£20,000,000 + add-ons", (20_000_000, "GBP")),
        ("€10m", (10_000_000, "EUR")),
        ("Undisclosed", (None, None)),
        ("", (None, None)),
    ],
)
def test_parse_money(text, expected):
    assert parse_money(text) == expected


@pytest.mark.parametrize(
    "text,kind,value",
    [
        ("£52,000,000", "Pago", 52_000_000),
        ("€10m", "Pago", None),  # outra moeda: não converte
        ("Undisclosed", "Não divulgado", None),
        ("Free Transfer", "Grátis", 0.0),
        ("Free", "Grátis", 0.0),
        ("Released", "Fim de contrato", 0.0),
        ("Loan", "Empréstimo", 0.0),
        ("Loan (£2m fee)", "Empréstimo", 2_000_000),
        ("Swap deal", "Outro", None),
    ],
)
def test_classify_fee(text, kind, value):
    assert classify_fee_gbp(text) == (kind, value)


def test_normalize_name():
    assert normalize_name("Luka Vušković") == "luka vuskovic"
    assert normalize_name("Pascal Groß") == "pascal gross"
    assert normalize_name("Martin Ødegaard") == "martin odegaard"


def test_parse_date():
    assert parse_date("15 June 2026") == date(2026, 6, 15)
    assert parse_date("15 June 2026 ") == date(2026, 6, 15)
    assert parse_date("30/06/2026") == date(2026, 6, 30)
    assert parse_date("End of Season") is None


@pytest.mark.parametrize(
    "raw,canon",
    [
        ("Brighton & Hove Albion FC", "Brighton & Hove Albion"),
        ("Brighton & Hove Albion F.C.", "Brighton & Hove Albion"),
        ("Brighton", "Brighton & Hove Albion"),
        ("AFC Bournemouth", "Bournemouth"),
        ("Hull City A.F.C.", "Hull City"),
        ("Hull City AFC", "Hull City"),
        ("Sunderland AFC", "Sunderland"),
        ("Nott'm Forest", "Nottingham Forest"),
        ("Man City", "Manchester City"),
        ("Wolverhampton Wanderers FC", "Wolverhampton Wanderers"),
    ],
)
def test_canonical_team(raw, canon):
    assert canonical_team(raw) == canon


def test_team_id():
    assert team_id("Brighton & Hove Albion F.C.") == "brighton-hove-albion"
    assert team_id("Brighton") == team_id("Brighton & Hove Albion FC")
