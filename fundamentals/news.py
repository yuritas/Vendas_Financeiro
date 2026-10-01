"""Notícias + sentimento com IA (Claude).

1. Coleta manchetes recentes dos feeds RSS configurados.
2. Envia ao Claude junto com os eventos do calendário já divulgados.
3. Recebe: viés por moeda (-5..+5) e os resultados ("actual") dos eventos
   que aparecerem nas manchetes — estes alimentam o calendar.py.
"""
import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone

import feedparser

import config
import db
from . import CURRENCIES
from . import calendar as cal

PROMPT = """Você é um analista fundamentalista de forex. Abaixo há manchetes recentes \
e uma lista de eventos econômicos já divulgados (com a previsão do mercado).

Tarefas:
1. Para cada moeda em {currencies}, dê uma nota de -5 (muito baixista) a +5 (muito altista) \
para as próximas 24h, considerando política monetária, dados, risco geopolítico e fluxo. \
Use 0 quando não houver informação. Inclua um motivo curto em português.
2. Para cada evento da lista cujo RESULTADO apareça explicitamente nas manchetes, informe \
o valor no mesmo formato da previsão (ex.: "0.4%", "120K"). Não invente valores.

Responda SOMENTE com JSON neste formato:
{{"currencies": {{"USD": {{"score": 0, "reason": "..."}}}},
 "actuals": [{{"key": "<key do evento>", "actual": "<valor>"}}]}}

EVENTOS DIVULGADOS:
{events}

MANCHETES:
{headlines}
"""


def fetch_headlines() -> list[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.NEWS_LOOKBACK_HOURS)
    out = []
    for url in config.NEWS_FEEDS:
        try:
            feed = feedparser.parse(url)
        except Exception as ex:  # feed fora do ar não derruba a análise
            db.log(f"Feed {url} falhou: {ex}", "WARN")
            continue
        for it in feed.entries:
            t = it.get("published_parsed") or it.get("updated_parsed")
            if t and datetime.fromtimestamp(time.mktime(t), timezone.utc) < cutoff:
                continue
            title = it.get("title", "").strip()
            summary = re.sub("<[^>]+>", "", it.get("summary", ""))[:200].strip()
            if title:
                out.append(f"- {title}" + (f" — {summary}" if summary else ""))
    return out[:120]


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("Resposta da IA sem JSON")
    return json.loads(m.group(0))


def analyze() -> tuple[dict, list[str]]:
    """Retorna (nota por moeda, motivos). Sem chave de API, retorna zeros."""
    zero = {c: 0.0 for c in CURRENCIES}
    if not config.ANTHROPIC_API_KEY:
        return zero, ["IA desativada (sem ANTHROPIC_API_KEY)"]

    headlines = fetch_headlines()
    events = [
        {"key": cal.event_key(e), "currency": e["country"], "title": e["title"],
         "time": e["dt"].isoformat(), "forecast": e.get("forecast")}
        for e in cal.recent_released()
    ]
    if not headlines:
        return zero, ["Sem manchetes recentes"]

    # Evita pagar a mesma análise duas vezes se nada mudou
    digest = hashlib.sha256(json.dumps([headlines, events]).encode()).hexdigest()
    cached = db.get_kv("news_cache")
    if cached and cached.get("digest") == digest:
        return cached["scores"], cached["notes"]

    import anthropic
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": PROMPT.format(
            currencies=", ".join(CURRENCIES),
            events=json.dumps(events, ensure_ascii=False, indent=0) or "[]",
            headlines="\n".join(headlines),
        )}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    data = _parse_json(text)

    valid_keys = {e["key"] for e in events}
    cal.set_actuals([a for a in data.get("actuals", []) if a.get("key") in valid_keys])

    scores, notes = dict(zero), []
    for c, v in (data.get("currencies") or {}).items():
        if c in scores:
            scores[c] = max(-5.0, min(5.0, float(v.get("score", 0))))
            if scores[c] and v.get("reason"):
                notes.append(f"{c} {scores[c]:+.0f}: {v['reason']}")
    db.set_kv("news_cache", {"digest": digest, "scores": scores, "notes": notes})
    return scores, notes
