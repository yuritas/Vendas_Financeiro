"""Aprendizado com os erros — ajustes estatísticos, pequenos, registrados e reversíveis.

Princípios:
* Só mexe em parâmetros com AMOSTRA MÍNIMA (poucos trades = ruído, não padrão).
* Passos pequenos e com limites (nada de "otimizar" até virar sobreajuste).
* Correções nunca AUMENTAM o risco por trade além do configurado.
* Cada correção é gravada com justificativa e evidência, aparece no painel,
  é avisada no WhatsApp e pode ser desfeita.
"""
import copy

import config
import db

DEFAULTS = {
    "weights": {"calendario": config.W_CALENDAR, "noticias": config.W_NEWS, "juros": config.W_MACRO},
    "threshold_adj": 0.0,          # soma ao SIGNAL_THRESHOLD em todos os pares
    "symbol_adj": {},              # soma extra por par
    "risk_mult": 1.0,              # multiplica RISK_PER_TRADE (só reduz)
    "blackout_min": config.NEWS_BLACKOUT_MIN,
    "sl_atr_mult": config.SL_ATR_MULT,
    "trend_filter": False,         # só opera a favor da tendência H4
}
LIMITS = {
    "weights": (0.3, 1.7), "threshold_adj": (0.0, 1.5), "symbol_adj": (0.0, 2.0),
    "risk_mult": (0.25, 1.0), "blackout_min": (config.NEWS_BLACKOUT_MIN, 120),
    "sl_atr_mult": (config.SL_ATR_MULT, max(config.SL_ATR_MULT, 2.5)),
}
LABELS = {
    "weights": "Peso do pilar", "threshold_adj": "Exigência mínima de nota (todos os pares)",
    "symbol_adj": "Exigência extra de nota no par", "risk_mult": "Multiplicador de risco",
    "blackout_min": "Janela de bloqueio por notícia (min)", "sl_atr_mult": "Distância do stop (× ATR)",
    "trend_filter": "Filtro de tendência H4",
}


# ---------------- parâmetros vigentes ----------------
def params() -> dict:
    p = copy.deepcopy(DEFAULTS)
    saved = db.get_kv("params", {}) or {}
    for k, v in saved.items():
        if isinstance(v, dict) and isinstance(p.get(k), dict):
            p[k].update(v)
        else:
            p[k] = v
    return p


def _set(kind: str, target: str, value) -> None:
    saved = db.get_kv("params", {}) or {}
    if kind in ("weights", "symbol_adj"):
        saved.setdefault(kind, {})[target] = value
    else:
        saved[kind] = value
    db.set_kv("params", saved)


def _get(kind: str, target: str):
    p = params()
    return p[kind].get(target, 0.0) if kind == "symbol_adj" else p[kind][target] if kind == "weights" else p[kind]


def threshold(symbol: str) -> float:
    p = params()
    return config.SIGNAL_THRESHOLD + p["threshold_adj"] + p["symbol_adj"].get(symbol, 0.0)


def _clamp(kind, v):
    lo, hi = LIMITS.get(kind, (None, None))
    if lo is None:
        return v
    return round(max(lo, min(hi, v)), 2)


# ---------------- registro de correções ----------------
def _cooldown_ok(key: str, n_closed: int, gap: int) -> bool:
    last = (db.get_kv("last_change", {}) or {}).get(key)
    return last is None or n_closed - last >= gap


def _mark(key: str, n_closed: int) -> None:
    lc = db.get_kv("last_change", {}) or {}
    lc[key] = n_closed
    db.set_kv("last_change", lc)


def apply(kind: str, target: str, new, justification: str, evidence: dict, n_closed: int) -> dict | None:
    old = _get(kind, target)
    new = new if isinstance(new, bool) else _clamp(kind, new)
    if new == old:
        return None
    _set(kind, target, new)
    _mark(f"{kind}:{target}", n_closed)
    cid = db.add_correction(kind, target, old, new, justification, evidence)
    db.log(f"Correção #{cid}: {LABELS.get(kind, kind)} [{target}] {old} → {new} — {justification}", "WARN")
    return {"id": cid, "kind": kind, "target": target, "old": old, "new": new, "justification": justification}


def revert(cid: int, by: str) -> str:
    c = db.get_correction(cid)
    if not c:
        return f"Correção #{cid} não existe."
    if c["reverted"]:
        return f"Correção #{cid} já foi desfeita."
    _set(c["kind"], c["target"], c["old_value"])
    db.mark_reverted(cid)
    # impede o sistema de refazer a mesma correção logo em seguida
    n = len(db.closed_trades_chrono(10**6))
    _mark(f"{c['kind']}:{c['target']}", n + 20)
    db.log(f"Correção #{cid} desfeita por {by}")
    return f"↩️ Correção #{cid} desfeita: {LABELS.get(c['kind'], c['kind'])} [{c['target']}] voltou para {c['old_value']}."


# ---------------- estatística ----------------
def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _corr(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = _mean(xs), _mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return 0.0 if sxx == 0 or syy == 0 else sxy / (sxx * syy) ** 0.5


def _aligned(t: dict, pillar: str) -> float:
    """Contribuição do pilar NA DIREÇÃO do trade (positivo = pilar apoiava a entrada)."""
    raw = (t.get("pillars") or {}).get(pillar, 0.0)
    return raw if t["direction"] == "BUY" else -raw


def _cats(t: dict) -> set:
    return {c["code"] for c in ((t.get("diagnosis") or {}).get("categories") or [])}


# ---------------- revisão após cada trade fechado ----------------
def review(trade: dict) -> list[dict]:
    if not config.LEARNING_ENABLED:
        return []
    hist = db.closed_trades_chrono(config.LEARN_WINDOW)
    n_closed = len(db.closed_trades_chrono(10**6))
    p = params()
    out = []

    def add(c):
        if c:
            out.append(c)

    # 1) Sequência de perdas -> reduz risco; primeira vitória -> restaura
    streak = 0
    for t in reversed(hist):
        if (t["r_multiple"] or 0) < 0:
            streak += 1
        else:
            break
    if streak >= config.MAX_CONSEC_LOSSES and p["risk_mult"] > 0.5:
        add(apply("risk_mult", "global", 0.5,
                  f"{streak} perdas seguidas: risco reduzido à metade até a próxima operação vencedora.",
                  {"perdas_seguidas": streak}, n_closed))
    elif streak == 0 and (trade["r_multiple"] or 0) > 0 and p["risk_mult"] < 1.0:
        add(apply("risk_mult", "global", 1.0, "Operação vencedora após sequência de perdas: risco restaurado.",
                  {"r_ultimo": trade["r_multiple"]}, n_closed))

    # 2) Desempenho por par -> exige nota maior onde o sistema erra mais
    sym = trade["symbol"]
    st = [t for t in hist if t["symbol"] == sym]
    if len(st) >= config.SYMBOL_MIN_TRADES and _cooldown_ok(f"symbol_adj:{sym}", n_closed, 4):
        exp = _mean([t["r_multiple"] or 0 for t in st])
        cur = p["symbol_adj"].get(sym, 0.0)
        ev = {"trades": len(st), "expectativa_R": round(exp, 2)}
        if exp < -0.25:
            add(apply("symbol_adj", sym, cur + 0.5,
                      f"{sym} com expectativa de {exp:+.2f}R em {len(st)} trades: exigindo nota maior para entrar.",
                      ev, n_closed))
        elif exp > 0.3 and cur > 0:
            add(apply("symbol_adj", sym, cur - 0.5,
                      f"{sym} recuperou ({exp:+.2f}R em {len(st)} trades): exigência extra reduzida.", ev, n_closed))

    # 3) Pesos dos pilares -> pilar que "acerta" ganha peso, que "erra" perde
    if len(hist) >= config.LEARN_MIN_TRADES and _cooldown_ok("weights:all", n_closed, 10):
        rs = [t["r_multiple"] or 0 for t in hist]
        changed = False
        for pillar in DEFAULTS["weights"]:
            xs = [_aligned(t, pillar) for t in hist]
            if not any(xs):
                continue
            c = _corr(xs, rs)
            agree = [r for x, r in zip(xs, rs) if x > 0.5]
            other = [r for x, r in zip(xs, rs) if x <= 0.5]
            ev = {"trades": len(hist), "correlacao": round(c, 2),
                  "R_quando_apoiou": round(_mean(agree), 2), "R_demais": round(_mean(other), 2)}
            w = p["weights"][pillar]
            if c > 0.15:
                r = apply("weights", pillar, w + 0.1,
                          f"Quando o pilar '{pillar}' apoiava a entrada o resultado foi melhor (correlação {c:+.2f}).",
                          ev, n_closed)
            elif c < -0.15:
                r = apply("weights", pillar, w - 0.1,
                          f"O pilar '{pillar}' tem acertado pouco (correlação {c:+.2f} com o resultado).",
                          ev, n_closed)
            else:
                r = None
            if r:
                changed = True
                add(r)
        if changed:
            _mark("weights:all", n_closed)

    # 4) Padrões nos diagnósticos das perdas — só conta perdas DEPOIS da última mudança
    #    daquele parâmetro, para não reagir duas vezes à mesma evidência.
    last_change = db.get_kv("last_change", {}) or {}
    offset = n_closed - len(hist)

    def recent_losses(key):
        since = last_change.get(key, -1)
        return [t for i, t in enumerate(hist) if offset + i + 1 > since and (t["r_multiple"] or 0) < 0][-10:]

    rules = (
        ("noticia_durante", "blackout_min", 0.4, lambda: p["blackout_min"] + 15,
         "das últimas perdas foram atingidas por notícia forte: janela de bloqueio ampliada."),
        ("stop_rapido", "sl_atr_mult", 0.5, lambda: p["sl_atr_mult"] + 0.25,
         "das últimas perdas foram stops na primeira hora (ruído): stop mais largo, "
         "com lote menor para manter o mesmo risco."),
        ("entrada_fraca", "threshold_adj", 0.5, lambda: p["threshold_adj"] + 0.25,
         "das últimas perdas vieram de sinais no limite mínimo: exigência de nota elevada."),
    )
    for code, kind, min_freq, new_value, text in rules:
        losses = recent_losses(f"{kind}:global")
        if len(losses) < 5:
            continue
        f = sum(code in _cats(t) for t in losses) / len(losses)
        if f >= min_freq:
            add(apply(kind, "global", new_value(), f"{f:.0%} {text}",
                      {"perdas_analisadas": len(losses), "frequencia": round(f, 2)}, n_closed))

    # 5) Tendência: liga o filtro se operar contra a tendência for claramente pior
    if not p["trend_filter"] and _cooldown_ok("trend_filter:global", n_closed, 10):
        pro = [t["r_multiple"] or 0 for t in hist if (t.get("context") or {}).get("trend_aligned") is True]
        con = [t["r_multiple"] or 0 for t in hist if (t.get("context") or {}).get("trend_aligned") is False]
        if len(pro) >= 10 and len(con) >= 10 and _mean(pro) - _mean(con) > 0.4:
            add(apply("trend_filter", "global", True,
                      f"Entradas contra a tendência H4 renderam {_mean(con):+.2f}R contra {_mean(pro):+.2f}R "
                      f"a favor: passando a operar só a favor da tendência.",
                      {"a_favor": len(pro), "contra": len(con)}, n_closed))
    return out


def describe(c: dict) -> str:
    return (f"🔧 *Correção #{c['id']}* — {LABELS.get(c['kind'], c['kind'])} [{c['target']}]: "
            f"{c['old']} → {c['new']}\n{c['justification']}\nPara desfazer: *desfazer {c['id']}*")
