"""Motor: roda a análise e abre operações (automático) ou cria sinais (confirmação)."""
import threading
from datetime import datetime, timedelta, timezone

import config
import db
import learning
import mt5_client as mt5c
import risk
import trades
import whatsapp
from fundamentals import calendar as cal
from fundamentals import scorer

_last = {"scores": None, "at": None}
_decision_lock = threading.Lock()   # evita decisão dupla (WhatsApp + web ao mesmo tempo)
_cycle_lock = threading.Lock()


def last_scores():
    return _last


def fmt_signal(s: dict) -> str:
    arrow = "🟢 COMPRA" if s["direction"] == "BUY" else "🔴 VENDA"
    reasons = "\n".join(f"• {r}" for r in s["reasons"][:5])
    return (f"*Sinal #{s['id']}* — {arrow} {s['symbol']}\nNota: {s['score']:+.1f}\n{reasons}\n\n"
            f"Responda *SIM {s['id']}* para executar ou *NAO {s['id']}* para descartar "
            f"(expira em {config.SIGNAL_EXPIRY_MIN} min).")


def _skip(symbol: str, score: float, why: str) -> None:
    db.log(f"{symbol}: oportunidade {score:+.1f} descartada — {why}")


def run_cycle() -> list[int]:
    """Uma rodada de análise. Retorna ids das operações abertas (auto) ou sinais criados (confirm)."""
    with _cycle_lock:
        expire()
        cs = scorer.currency_scores()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _last.update(scores=cs, at=now)
        db.set_kv("last_scores", {"total": cs["total"], "at": now})
        if risk.is_paused():
            db.log("Ciclo de análise feito (sistema pausado — nada aberto)")
            return []

        p = learning.params()
        out = []
        for symbol in config.SYMBOLS:
            score, reasons, pillars = scorer.pair_score(symbol, cs)
            thr = round(learning.threshold(symbol), 2)
            if abs(score) < thr or db.has_pending(symbol):
                continue
            direction = "BUY" if score > 0 else "SELL"
            blocked = (cal.upcoming_high_impact(symbol[:3], p["blackout_min"])
                       or cal.upcoming_high_impact(symbol[3:6], p["blackout_min"]))
            if blocked:
                _skip(symbol, score, f"notícia forte próxima: {blocked['country']} {blocked['title']}")
                continue
            if p["trend_filter"]:
                tr = mt5c.trend(symbol)
                if tr and tr != (1 if direction == "BUY" else -1):
                    _skip(symbol, score, "contra a tendência H4 (filtro ligado pelo aprendizado)")
                    continue
            ok, why = risk.can_open(symbol)
            if not ok:
                _skip(symbol, score, why)
                continue
            try:
                if config.EXECUTION_MODE == "auto":
                    tid, _ = trades.open_trade(symbol, direction, score, pillars, reasons, thr)
                    out.append(tid)
                else:
                    expires = datetime.now(timezone.utc) + timedelta(minutes=config.SIGNAL_EXPIRY_MIN)
                    sid = db.add_signal(symbol=symbol, direction=direction, score=score, reasons=reasons,
                                        expires_at=expires.isoformat(timespec="seconds"))
                    db.set_kv(f"signal_ctx:{sid}", {"pillars": pillars, "threshold": thr})
                    out.append(sid)
                    db.log(f"Sinal #{sid} criado: {direction} {symbol} nota {score:+.1f}")
                    whatsapp.broadcast(fmt_signal(db.get_signal(sid)))
            except Exception as ex:
                db.log(f"{symbol}: falha ao abrir/sinalizar: {ex}", "ERROR")
                whatsapp.broadcast(f"⚠️ Falha ao abrir {direction} {symbol}: {ex}")
        return out


def expire() -> None:
    for sid in db.expire_pending():
        db.log(f"Sinal #{sid} expirou")


# ---------- modo confirmação ----------
def approve(sid: int, by: str) -> str:
    with _decision_lock:
        s = db.get_signal(sid)
        if not s:
            return f"Sinal #{sid} não existe."
        expire()
        s = db.get_signal(sid)
        if s["status"] != "pending":
            return f"Sinal #{sid} está '{s['status']}', não pode ser executado."
        ok, why = risk.can_open(s["symbol"])
        if not ok:
            db.update_signal(sid, status="rejected", decided_by="risco", decided_at=db.now_iso(), error=why)
            return f"Sinal #{sid} bloqueado pelo risco: {why}"
        ctx = db.get_kv(f"signal_ctx:{sid}", {}) or {}
        db.update_signal(sid, status="approved", decided_by=by, decided_at=db.now_iso())
        try:
            tid, msg = trades.open_trade(s["symbol"], s["direction"], s["score"], ctx.get("pillars", {}),
                                         s["reasons"], ctx.get("threshold", config.SIGNAL_THRESHOLD), sid, by)
            db.update_signal(sid, status="executed", ticket=tid)
            return f"✅ Sinal #{sid} executado como trade #{tid}."
        except Exception as ex:
            db.update_signal(sid, status="failed", error=str(ex))
            db.log(f"Sinal #{sid} falhou: {ex}", "ERROR")
            return f"❌ Sinal #{sid} falhou: {ex}"


def reject(sid: int, by: str) -> str:
    with _decision_lock:
        s = db.get_signal(sid)
        if not s:
            return f"Sinal #{sid} não existe."
        if s["status"] != "pending":
            return f"Sinal #{sid} já está '{s['status']}'."
        db.update_signal(sid, status="rejected", decided_by=by, decided_at=db.now_iso())
        db.log(f"Sinal #{sid} descartado por {by}")
        return f"Sinal #{sid} descartado."


def status() -> dict:
    acc = mt5c.account()
    paper, why = trades.paper_mode() if acc else (True, "sem conexão")
    return {
        "account": acc,
        "daily_pnl": trades.daily_pnl() if acc else None,
        "paused": risk.is_paused(),
        "dry_run": config.DRY_RUN,
        "mode": config.EXECUTION_MODE,
        "paper": paper, "paper_reason": why,
        "open_trades": trades.open_with_floating(),
        "manual_positions": [p for p in mt5c.positions() if not p["bot"]],
        "pending": db.list_signals(20, "pending"),
        "last_analysis": _last["at"],
    }


def daily_report() -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    closed = [t for t in db.list_trades(500, "closed") if (t["closed_at"] or "")[:10] == today]
    st = trades.stats()
    lines = [f"📊 *Resumo do dia* — {len(closed)} operação(ões) encerrada(s)"]
    for t in closed:
        lines.append(f"• #{t['id']} {t['direction']} {t['symbol']}: {t['r_multiple']:+.2f}R ({t['exit_reason']})")
    lines += [
        f"Resultado do dia: {trades.daily_pnl():+.2f}",
        f"Acumulado: {st['trades']} trades | acerto {st['win_rate']:.0%} | expectativa {st['expectancy_r']:+.2f}R"
        f" | DD máx {st['max_drawdown']:.2f}",
        f"Abertas agora: {len(db.list_trades(100, 'open'))}",
    ]
    corr = [c for c in db.list_corrections(20) if c["ts"][:10] == today]
    if corr:
        lines.append(f"Correções hoje: {len(corr)} — veja o painel.")
    msg = "\n".join(lines)
    whatsapp.broadcast(msg)
    return msg
