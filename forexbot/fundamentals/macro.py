"""Juros e postura dos bancos centrais.

Lê macro.json (você atualiza após cada reunião de banco central):
  "USD": {"rate": 4.25, "bias": "neutral"}   # bias: hawkish | neutral | dovish

Nota = diferencial de juros em relação à média (carry) + postura do BC.
"""
import json
import os

import config
from . import CURRENCIES

BIAS = {"hawkish": 2.0, "neutral": 0.0, "dovish": -2.0}


def load() -> dict:
    if not os.path.exists(config.MACRO_FILE):
        return {}
    with open(config.MACRO_FILE, encoding="utf-8") as f:
        return json.load(f)


def scores() -> tuple[dict, list[str]]:
    data = load()
    sc = {c: 0.0 for c in CURRENCIES}
    if not data:
        return sc, ["macro.json ausente — pilar de juros desligado"]
    rates = {c: float(v["rate"]) for c, v in data.items() if c in sc and "rate" in v}
    avg = sum(rates.values()) / len(rates) if rates else 0.0
    notes = []
    for c in CURRENCIES:
        v = data.get(c, {})
        carry = (rates.get(c, avg) - avg) * 0.75          # 1 p.p. acima da média ≈ +0.75
        stance = BIAS.get(str(v.get("bias", "neutral")).lower(), 0.0)
        sc[c] = max(-5.0, min(5.0, carry + stance))
        if abs(sc[c]) >= 1:
            notes.append(f"{c}: juros {rates.get(c, '?')}% ({v.get('bias', 'neutral')})")
    return sc, notes
