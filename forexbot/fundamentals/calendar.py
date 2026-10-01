"""Calendário econômico (feed semanal da Forex Factory).

O feed traz data, moeda, impacto, previsão e anterior — mas NÃO traz o resultado
("actual"). Os resultados são extraídos das manchetes pelo módulo news.py e
gravados aqui via set_actuals(). Com isso calculamos a "surpresa" de cada dado.
"""
import re
import time
from datetime import datetime, timedelta, timezone

import requests

import config
import db
from . import CURRENCIES

_cache = {"ts": 0.0, "events": []}
CACHE_SECONDS = 30 * 60  # o feed pede poucas requisições; 30 min é suficiente

# Indicadores em que número MAIOR é RUIM para a moeda
INVERSE = ("unemployment rate", "unemployment claims", "jobless", "claimant", "unemployment change")
IMPACT_WEIGHT = {"High": 3.0, "Medium": 1.5, "Low": 0.5}
DECAY_HOURS = 48


def fetch_events(force: bool = False) -> list[dict]:
    if not force and time.time() - _cache["ts"] < CACHE_SECONDS and _cache["events"]:
        return _cache["events"]
    r = requests.get(config.CALENDAR_URL, timeout=20, headers={"User-Agent": "forexbot/1.0"})
    r.raise_for_status()
    events = []
    for e in r.json():
        if e.get("country") not in CURRENCIES:
            continue
        e["dt"] = datetime.fromisoformat(e["date"]).astimezone(timezone.utc)
        events.append(e)
    _cache.update(ts=time.time(), events=events)
    return events


def event_key(e: dict) -> str:
    return f'{e["country"]}|{e["title"]}|{e["date"]}'


def parse_num(s) -> float | None:
    """'0.3%' -> 0.3 ; '215K' -> 215000 ; '-1.2B' -> -1.2e9 ; '' -> None"""
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    m = re.match(r"^(-?\d+(?:\.\d+)?)\s*([KMBT%]?)", s, re.I)
    if not m:
        return None
    v = float(m.group(1))
    mult = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}.get(m.group(2).upper(), 1)
    return v * mult


def set_actuals(items: list[dict]) -> None:
    """items: [{"key": event_key, "actual": "0.4%"}] — guardados no banco."""
    actuals = db.get_kv("actuals", {})
    for it in items:
        if it.get("key") and it.get("actual") not in (None, ""):
            actuals[it["key"]] = str(it["actual"])
    db.set_kv("actuals", actuals)


def recent_released(hours: int = 24) -> list[dict]:
    """Eventos com previsão já divulgados nas últimas `hours` horas (p/ a IA buscar o resultado)."""
    now = datetime.now(timezone.utc)
    return [
        e for e in fetch_events()
        if e["impact"] in ("High", "Medium") and e.get("forecast")
        and now - timedelta(hours=hours) <= e["dt"] <= now
    ]


def surprise(e: dict, actual: float) -> float:
    fc = parse_num(e.get("forecast"))
    if fc is None:
        return 0.0
    denom = max(abs(fc), 1e-9)
    # dados em % (ex.: CPI 0.3%) variam pouco: usa escala absoluta de 0.2 p.p.
    if str(e.get("forecast", "")).strip().endswith("%"):
        s = (actual - fc) / 0.2
    else:
        s = (actual - fc) / denom * 5
    s = max(-1.0, min(1.0, s))
    if any(k in e["title"].lower() for k in INVERSE):
        s = -s
    return s


def scores() -> tuple[dict, list[str]]:
    """Nota por moeda (aprox. -5..+5) baseada nas surpresas recentes."""
    actuals = db.get_kv("actuals", {})
    now = datetime.now(timezone.utc)
    sc = {c: 0.0 for c in CURRENCIES}
    notes = []
    for e in fetch_events():
        a = actuals.get(event_key(e))
        if a is None or e["dt"] > now:
            continue
        av = parse_num(a)
        if av is None:
            continue
        age_h = (now - e["dt"]).total_seconds() / 3600
        if age_h > DECAY_HOURS:
            continue
        s = surprise(e, av) * IMPACT_WEIGHT.get(e["impact"], 0) * (1 - age_h / DECAY_HOURS)
        if abs(s) < 0.05:
            continue
        sc[e["country"]] += s
        notes.append(f'{e["country"]} {e["title"]}: {a} vs esperado {e["forecast"]} ({s:+.1f})')
    return {c: max(-5.0, min(5.0, v)) for c, v in sc.items()}, notes


def upcoming_high_impact(currency: str, minutes: int | None = None) -> dict | None:
    """Retorna o evento de alto impacto da moeda dentro da janela de bloqueio, se houver."""
    minutes = minutes if minutes is not None else config.NEWS_BLACKOUT_MIN
    now = datetime.now(timezone.utc)
    for e in fetch_events():
        if e["country"] == currency and e["impact"] == "High":
            if abs((e["dt"] - now).total_seconds()) <= minutes * 60:
                return e
    return None


def next_events(limit: int = 10) -> list[dict]:
    now = datetime.now(timezone.utc)
    evs = [e for e in fetch_events() if e["dt"] >= now and e["impact"] in ("High", "Medium")]
    evs.sort(key=lambda e: e["dt"])
    return [
        {"time": e["dt"].isoformat(), "currency": e["country"], "title": e["title"],
         "impact": e["impact"], "forecast": e.get("forecast", ""), "previous": e.get("previous", "")}
        for e in evs[:limit]
    ]
