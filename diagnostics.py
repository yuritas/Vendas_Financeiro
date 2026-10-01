"""Diagnóstico de cada operação fechada: o que deu certo/errado e por quê.

Duas camadas:
1. Regras objetivas (sempre): categorias que o módulo de aprendizado usa.
2. Explicação da IA (opcional, com ANTHROPIC_API_KEY): texto e lição aprendida.
   A IA NÃO altera parâmetros — só as regras estatísticas do learning.py fazem isso.
"""
import json
import re
from datetime import datetime

import config
import db
from fundamentals import calendar as cal

CATS = {
    "alvo_atingido": "Alvo atingido — tese confirmada",
    "noticia_durante": "Notícia de alto impacto durante a operação",
    "stop_rapido": "Stop na primeira hora (ruído/entrada mal posicionada)",
    "fundamento_virou": "Fundamentos do par mudaram depois da entrada",
    "entrada_fraca": "Sinal no limite mínimo de nota",
    "contra_tendencia": "Entrada contra a tendência H4",
    "spread_alto": "Spread alto na entrada",
    "saida_manual": "Encerrada manualmente",
}


def _dt(s):
    return datetime.fromisoformat(s)


def categorize(t: dict, current_pair_score: float | None) -> list[dict]:
    codes = []
    r = t.get("r_multiple") or 0
    ctx = t.get("context") or {}
    opened, closed = _dt(t["opened_at"]), _dt(t["closed_at"])
    minutes = (closed - opened).total_seconds() / 60

    if t.get("exit_reason") == "TP":
        codes.append("alvo_atingido")
    if t.get("exit_reason") == "MANUAL":
        codes.append("saida_manual")

    try:
        base, quote = t["symbol"][:3], t["symbol"][3:6]
        for e in cal.fetch_events():
            if e["impact"] == "High" and e["country"] in (base, quote) and opened <= e["dt"] <= closed:
                if r < 0:
                    codes.append("noticia_durante")
                break
    except Exception:
        pass

    if r < 0 and t.get("exit_reason") == "SL" and minutes <= 60:
        codes.append("stop_rapido")
    if r < 0 and current_pair_score is not None and t.get("score"):
        same_side = (current_pair_score > 0) == (t["score"] > 0)
        if not same_side or abs(current_pair_score) < abs(t["score"]) / 2:
            codes.append("fundamento_virou")
    thr = ctx.get("threshold")
    if r < 0 and thr and abs(t.get("score") or 0) < thr + 0.5:
        codes.append("entrada_fraca")
    if ctx.get("trend_aligned") is False:
        codes.append("contra_tendencia")
    if (t.get("spread") or 0) > config.MAX_SPREAD_POINTS * 0.6:
        codes.append("spread_alto")
    return [{"code": c, "label": CATS[c]} for c in dict.fromkeys(codes)]


def _summary(t: dict, cats: list[dict]) -> str:
    r = t.get("r_multiple") or 0
    res = "ganho" if r > 0 else "perda" if r < 0 else "zero a zero"
    why = "; ".join(c["label"].lower() for c in cats) or "sem fator de erro identificado — variação normal do mercado"
    return f"{res.capitalize()} de {r:+.2f}R ({t.get('exit_reason')}). Fatores: {why}."


PROMPT = """Você é um mentor de trading fundamentalista em forex. Analise esta operação já \
encerrada e explique, em português e de forma objetiva (até 5 frases), por que deu o resultado \
que deu e qual a lição prática. Não invente fatos além dos dados. Depois dê UMA sugestão concreta \
de melhoria do sistema (pode ser "nenhuma" se foi variação normal).

Responda só com JSON: {{"analise": "...", "licao": "...", "sugestao": "..."}}

OPERAÇÃO:
{trade}

CATEGORIAS DETECTADAS: {cats}
"""


def _ai(t: dict, cats: list[dict]) -> dict | None:
    if not config.ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
        slim = {k: t.get(k) for k in ("symbol", "direction", "entry", "sl", "tp", "exit_price", "exit_reason",
                                      "r_multiple", "opened_at", "closed_at", "score", "pillars", "reasons", "context")}
        msg = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY).messages.create(
            model=config.ANTHROPIC_MODEL, max_tokens=700,
            messages=[{"role": "user", "content": PROMPT.format(
                trade=json.dumps(slim, ensure_ascii=False, default=str),
                cats=", ".join(c["label"] for c in cats) or "nenhuma")}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    except Exception as ex:
        db.log(f"Diagnóstico por IA falhou: {ex}", "WARN")
        return None


def diagnose(t: dict, current_pair_score: float | None) -> dict:
    cats = categorize(t, current_pair_score)
    d = {"categories": cats, "summary": _summary(t, cats), "pair_score_at_close": current_pair_score}
    ai = _ai(t, cats)
    if ai:
        d.update(ai=True, analise=ai.get("analise"), licao=ai.get("licao"), sugestao=ai.get("sugestao"))
    return d
