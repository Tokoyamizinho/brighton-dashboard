"""Funções utilitárias de limpeza: dinheiro, nomes, datas."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

_MONEY_RE = re.compile(
    r"([£€$])\s*([\d.,]+)\s*(bn|billion|m|million|mil|k|thousand)?\b", re.IGNORECASE
)
_MULT = {"bn": 1e9, "billion": 1e9, "m": 1e6, "million": 1e6, "mil": 1e3, "k": 1e3, "thousand": 1e3}


def parse_money(text: str | None) -> tuple[float | None, str | None]:
    """'£52,000,000' -> (52_000_000, 'GBP') ; '£6.5m' -> (6_500_000, 'GBP') ;
    '€10m' -> (10_000_000, 'EUR') ; 'Undisclosed' -> (None, None)."""
    if not text:
        return None, None
    m = _MONEY_RE.search(text.replace("\xa0", " "))
    if not m:
        return None, None
    symbol, num, unit = m.group(1), m.group(2), (m.group(3) or "").lower()
    # "1,234,567" (inglês) ou "1.234.567" (europeu)
    if "," in num and "." in num:
        num = num.replace(".", "").replace(",", ".") if num.rfind(",") > num.rfind(".") else num.replace(",", "")
    elif num.count(",") >= 1 and len(num.split(",")[-1]) == 3:
        num = num.replace(",", "")
    elif num.count(".") > 1:
        num = num.replace(".", "")
    else:
        num = num.replace(",", ".")
    try:
        value = float(num)
    except ValueError:
        return None, None
    currency = {"£": "GBP", "€": "EUR", "$": "USD"}[symbol]
    return value * _MULT.get(unit, 1), currency


def classify_fee_gbp(text: str | None) -> tuple[str, float | None]:
    """Classifica o texto da coluna "Fee" da Wikipedia.

    Retorna (tipo, valor_em_libras). Tipos: "Pago", "Não divulgado", "Grátis",
    "Empréstimo", "Fim de contrato", "Outro". Valores em outra moeda não são
    convertidos (ficam como "Pago" sem valor) para não inventar câmbio.
    """
    t = (text or "").strip()
    low = t.lower()
    value, currency = parse_money(t)
    if "loan" in low:
        return "Empréstimo", value if currency == "GBP" else (0.0 if value is None else None)
    if value is not None:
        return "Pago", value if currency == "GBP" else None
    if not t or "undisclosed" in low or t in {"-", "?", "—", "N/A"}:
        return "Não divulgado", None
    if "free" in low:
        return "Grátis", 0.0
    if any(k in low for k in ("released", "retired", "end of contract", "contract expired", "mutual")):
        return "Fim de contrato", 0.0
    return "Outro", None


# letras que o NFKD não decompõe em "letra + acento"
_SPECIAL = str.maketrans({"ß": "ss", "ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "đ": "d", "Đ": "D",
                          "ł": "l", "Ł": "L", "ı": "i", "œ": "oe", "þ": "th", "ð": "d"})


def normalize_name(name: str | None) -> str:
    """Remove acentos, pontuação e caixa: 'Pascal Groß' -> 'pascal gross'."""
    if not name:
        return ""
    nfkd = unicodedata.normalize("NFKD", name.translate(_SPECIAL))
    ascii_ = "".join(c for c in nfkd if not unicodedata.combining(c))
    ascii_ = re.sub(r"[^a-zA-Z\s-]", " ", ascii_).replace("-", " ")
    return re.sub(r"\s+", " ", ascii_).strip().lower()


_DATE_FORMATS = ("%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y", "%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d")


def parse_date(text: str | None) -> date | None:
    """'15 June 2026' / '30/06/2026' / '2026-06-30' -> date"""
    if not text:
        return None
    t = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None
