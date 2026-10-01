"""Combina os três pilares numa nota por moeda e por par (pesos vêm do aprendizado)."""
import db
import learning
from . import CURRENCIES
from . import calendar as cal
from . import macro, news

PILLARS = ("calendario", "noticias", "juros")


def currency_scores() -> dict:
    pillars, notes = {}, {}
    for name, fn in (("calendario", cal.scores), ("noticias", news.analyze), ("juros", macro.scores)):
        try:
            pillars[name], notes[name] = fn()
        except Exception as ex:
            db.log(f"Pilar {name} falhou: {ex}", "ERROR")
            pillars[name], notes[name] = {c: 0.0 for c in CURRENCIES}, [f"erro: {ex}"]

    w = learning.params()["weights"]
    total = {c: round(sum(w[p] * pillars[p][c] for p in PILLARS), 2) for c in CURRENCIES}
    return {"total": total, "pillars": pillars, "notes": notes, "weights": w}


def pair_score(symbol: str, cs: dict) -> tuple[float, list[str], dict]:
    """(nota do par, justificativas, diferença base−cotada de cada pilar sem peso)."""
    base, quote = symbol[:3], symbol[3:6]
    t = cs["total"]
    score = round(t.get(base, 0) - t.get(quote, 0), 2)
    breakdown = {p: round(cs["pillars"][p].get(base, 0) - cs["pillars"][p].get(quote, 0), 2) for p in PILLARS}
    reasons = [f"{base} {t.get(base, 0):+.1f} vs {quote} {t.get(quote, 0):+.1f} "
               f"(cal {breakdown['calendario']:+.1f} · notícias {breakdown['noticias']:+.1f} · "
               f"juros {breakdown['juros']:+.1f})"]
    for pillar, lines in cs["notes"].items():
        for line in lines:
            if line.startswith((base, quote)):
                reasons.append(f"[{pillar}] {line}")
    return score, reasons[:10], breakdown
