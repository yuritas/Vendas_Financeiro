"""Ciclo de vida das operações: abrir, acompanhar, fechar, diagnosticar e aprender.

Funciona igual em modo real e em modo simulado ("papel"): no simulado a operação
é registrada com o preço real do MT5 e o stop/alvo são verificados a cada minuto,
então o diário, os diagnósticos e o aprendizado funcionam desde o primeiro dia.
"""
import threading
from datetime import datetime, timezone

import config
import db
import diagnostics
import learning
import mt5_client as mt5c
import whatsapp

_lock = threading.RLock()


def paper_mode() -> tuple[bool, str]:
    if config.DRY_RUN:
        return True, "DRY_RUN ligado"
    acc = mt5c.account()
    if acc.get("trade_mode") == "real" and config.EXECUTION_MODE == "auto" and not config.ALLOW_REAL_AUTO:
        return True, "conta REAL em modo automático sem ALLOW_REAL_AUTO=true"
    return False, ""


def _levels(symbol: str, direction: str, p: dict):
    a = mt5c.atr(symbol)
    entry = mt5c.price(symbol, direction)
    d = mt5c.digits(symbol)
    sl_dist = a * p["sl_atr_mult"]
    tp_dist = sl_dist * (config.TP_ATR_MULT / config.SL_ATR_MULT)   # mantém a relação risco/retorno
    sign = 1 if direction == "BUY" else -1
    return round(entry, d), round(entry - sign * sl_dist, d), round(entry + sign * tp_dist, d), sl_dist, a


def fmt_open(t: dict) -> str:
    arrow = "🟢 COMPRA" if t["direction"] == "BUY" else "🔴 VENDA"
    tag = " _(simulado)_" if t["paper"] else f" ticket {t['ticket']}"
    ctx = t.get("context") or {}
    why = "\n".join(f"• {r}" for r in (t.get("reasons") or [])[:5])
    return (f"🤖 *Trade #{t['id']} aberto*{tag}\n{arrow} {t['symbol']} {t['volume']} lote\n"
            f"Entrada {t['entry']} | SL {t['sl']} | TP {t['tp']}\n"
            f"Nota {t['score']:+.1f} (mín. {ctx.get('threshold', 0):.1f}) | risco {t['risk_money']:.2f} "
            f"({ctx.get('risk_pct', 0):.2f}%)\n*Por quê:*\n{why}\n\nPara encerrar: *fechar {t['id']}*")


def fmt_close(t: dict) -> str:
    r = t["r_multiple"] or 0
    icon = "✅" if r > 0 else "❌" if r < 0 else "➖"
    d = t.get("diagnosis") or {}
    lines = [f"{icon} *Trade #{t['id']} encerrado* — {t['direction']} {t['symbol']}",
             f"Saída {t['exit_price']} ({t['exit_reason']}) | {t['profit']:+.2f} | *{r:+.2f}R*",
             f"Diagnóstico: {d.get('summary', '-')}"]
    if d.get("licao"):
        lines.append(f"Lição: {d['licao']}")
    return "\n".join(lines)


def open_trade(symbol: str, direction: str, score: float, pillars: dict, reasons: list[str],
               threshold: float, signal_id: int | None = None, by: str = "auto") -> tuple[int, str]:
    with _lock:
        p = learning.params()
        entry, sl, tp, sl_dist, atr = _levels(symbol, direction, p)
        risk_pct = round(config.RISK_PER_TRADE * p["risk_mult"], 3)
        volume = mt5c.calc_volume(symbol, sl_dist, risk_pct)
        trend = mt5c.trend(symbol)
        paper, paper_why = paper_mode()
        ticket = None
        if not paper:
            ticket = mt5c.send_market(symbol, direction, volume, sl, tp, f"fx#{signal_id or 'auto'}")
        tid = db.add_trade(
            signal_id=signal_id, ticket=ticket, paper=int(paper), symbol=symbol, direction=direction,
            volume=volume, entry=entry, sl=sl, tp=tp, atr=atr, spread=mt5c.spread_points(symbol),
            risk_money=round(mt5c.money_for_distance(symbol, sl_dist, volume), 2),
            score=score, pillars=pillars, reasons=reasons,
            context={
                "threshold": threshold, "weights": p["weights"], "risk_pct": risk_pct,
                "sl_atr_mult": p["sl_atr_mult"], "trend_h4": trend,
                "trend_aligned": None if trend == 0 else trend == (1 if direction == "BUY" else -1),
                "mode": config.EXECUTION_MODE, "paper_reason": paper_why, "opened_by": by,
            },
        )
        t = db.get_trade(tid)
        msg = fmt_open(t)
        db.log(f"Trade #{tid} aberto: {direction} {symbol} {volume} @ {entry}" + (" (simulado)" if paper else ""))
        whatsapp.broadcast(msg)
        return tid, msg


def _current_pair_score(symbol: str) -> float | None:
    cs = db.get_kv("last_scores")
    if not cs:
        return None
    t = cs["total"]
    return round(t.get(symbol[:3], 0) - t.get(symbol[3:6], 0), 2)


def _finalize(t: dict, exit_price: float, exit_reason: str, profit: float | None = None,
              closed_at: str | None = None) -> dict:
    sign = 1 if t["direction"] == "BUY" else -1
    if profit is None:
        profit = mt5c.money_for_distance(t["symbol"], sign * (exit_price - t["entry"]), t["volume"])
    r = profit / t["risk_money"] if t["risk_money"] else 0.0
    db.update_trade(t["id"], status="closed", exit_price=exit_price, exit_reason=exit_reason,
                    profit=round(profit, 2), r_multiple=round(r, 2), closed_at=closed_at or db.now_iso())
    t = db.get_trade(t["id"])
    try:
        db.update_trade(t["id"], diagnosis=diagnostics.diagnose(t, _current_pair_score(t["symbol"])))
    except Exception as ex:
        db.log(f"Diagnóstico do trade #{t['id']} falhou: {ex}", "ERROR")
    t = db.get_trade(t["id"])
    db.log(f"Trade #{t['id']} encerrado: {t['exit_reason']} {t['profit']:+.2f} ({t['r_multiple']:+.2f}R)")
    whatsapp.broadcast(fmt_close(t))
    try:
        for c in learning.review(t):
            whatsapp.broadcast(learning.describe(c))
    except Exception as ex:
        db.log(f"Revisão do aprendizado falhou: {ex}", "ERROR")
    return t


def monitor() -> None:
    """Roda a cada minuto: detecta stops/alvos (simulado) e fechamentos no MT5 (real)."""
    with _lock:
        for t in db.list_trades(1000, "open"):
            try:
                if t["paper"]:
                    bid, ask = mt5c.tick(t["symbol"])
                    if t["direction"] == "BUY":
                        hit = ("SL", t["sl"]) if bid <= t["sl"] else ("TP", t["tp"]) if bid >= t["tp"] else None
                    else:
                        hit = ("SL", t["sl"]) if ask >= t["sl"] else ("TP", t["tp"]) if ask <= t["tp"] else None
                    if hit:
                        _finalize(t, hit[1], hit[0])
                elif not mt5c.is_open(t["ticket"]):
                    info = mt5c.closed_info(t["ticket"])
                    if info:
                        _finalize(t, **info)
            except Exception as ex:
                db.log(f"Monitor trade #{t['id']}: {ex}", "ERROR")


def close_trade(tid: int, by: str) -> str:
    with _lock:
        t = db.get_trade(tid)
        if not t:
            return f"Trade #{tid} não existe."
        if t["status"] != "open":
            return f"Trade #{tid} já está encerrado."
        try:
            if t["paper"]:
                bid, ask = mt5c.tick(t["symbol"])
                _finalize(t, bid if t["direction"] == "BUY" else ask, "MANUAL")
            else:
                mt5c.close_position(t["ticket"])
                info = mt5c.closed_info(t["ticket"]) or {"exit_price": mt5c.price(t["symbol"], "SELL" if t["direction"] == "BUY" else "BUY")}
                info["exit_reason"] = "MANUAL"
                _finalize(t, **info)
        except Exception as ex:
            return f"❌ Falha ao encerrar trade #{tid}: {ex}"
        db.log(f"Trade #{tid} encerrado manualmente por {by}")
        return f"Trade #{tid} encerrado."


def close_all(by: str) -> str:
    msgs = [close_trade(t["id"], by) for t in db.list_trades(1000, "open")]
    return "\n".join(msgs) or "Nenhuma operação aberta."


def floating(t: dict) -> float:
    try:
        bid, ask = mt5c.tick(t["symbol"])
        px = bid if t["direction"] == "BUY" else ask
        sign = 1 if t["direction"] == "BUY" else -1
        return round(mt5c.money_for_distance(t["symbol"], sign * (px - t["entry"]), t["volume"]), 2)
    except Exception:
        return 0.0


def open_with_floating() -> list[dict]:
    out = []
    for t in db.list_trades(1000, "open"):
        t["floating"] = floating(t)
        t["floating_r"] = round(t["floating"] / t["risk_money"], 2) if t["risk_money"] else 0
        out.append(t)
    return out


def daily_pnl() -> float:
    today = datetime.now(timezone.utc).date().isoformat()
    closed = sum(t["profit"] or 0 for t in db.list_trades(1000, "closed") if (t["closed_at"] or "")[:10] == today)
    return round(closed + sum(floating(t) for t in db.list_trades(1000, "open")), 2)


# ---------------- estatísticas para o painel ----------------
def stats() -> dict:
    closed = db.closed_trades_chrono(10**6)
    n = len(closed)
    rs = [t["r_multiple"] or 0 for t in closed]
    pnl = [t["profit"] or 0 for t in closed]
    wins = [r for r in rs if r > 0]
    gross_win = sum(p for p in pnl if p > 0)
    gross_loss = -sum(p for p in pnl if p < 0)

    curve, cum, peak, mdd = [], 0.0, 0.0, 0.0
    for t in closed:
        cum += t["profit"] or 0
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
        curve.append({"t": t["closed_at"], "cum": round(cum, 2), "r": t["r_multiple"], "id": t["id"]})

    def group(key):
        g = {}
        for t in closed:
            g.setdefault(key(t), []).append(t)
        return {k: {"n": len(v), "win_rate": round(sum((x["r_multiple"] or 0) > 0 for x in v) / len(v), 3),
                    "avg_r": round(sum(x["r_multiple"] or 0 for x in v) / len(v), 2),
                    "profit": round(sum(x["profit"] or 0 for x in v), 2)} for k, v in g.items()}

    cats = {}
    for t in closed:
        if (t["r_multiple"] or 0) < 0:
            for c in ((t.get("diagnosis") or {}).get("categories") or []):
                cats[c["label"]] = cats.get(c["label"], 0) + 1

    pillar = {}
    for p in ("calendario", "noticias", "juros"):
        sup = [t["r_multiple"] or 0 for t in closed if learning._aligned(t, p) > 0.5]
        oth = [t["r_multiple"] or 0 for t in closed if learning._aligned(t, p) <= 0.5]
        pillar[p] = {"apoiou_n": len(sup), "apoiou_avg_r": round(learning._mean(sup), 2),
                     "demais_n": len(oth), "demais_avg_r": round(learning._mean(oth), 2)}

    return {
        "trades": n, "win_rate": round(len(wins) / n, 3) if n else 0,
        "expectancy_r": round(sum(rs) / n, 2) if n else 0,
        "profit": round(sum(pnl), 2), "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
        "max_drawdown": round(mdd, 2), "curve": curve,
        "by_symbol": group(lambda t: t["symbol"]), "by_exit": group(lambda t: t["exit_reason"] or "?"),
        "loss_causes": dict(sorted(cats.items(), key=lambda kv: -kv[1])),
        "by_pillar": pillar, "params": learning.params(),
        "min_trades_for_learning": config.LEARN_MIN_TRADES,
    }
