"""Ponto de entrada: API web + webhook do WhatsApp + agendador de análises.

Uso (no Windows, com o MetaTrader 5 aberto e logado):
    python main.py
"""
import secrets

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse

import commands
import config
import db
import engine
import learning
import mt5_client as mt5c
import risk
import trades
import whatsapp
from fundamentals import calendar as cal

app = FastAPI(title="ForexBot")


# ---------- autenticação do painel ----------
def auth(authorization: str = Header(default="")):
    token = authorization.removeprefix("Bearer ").strip()
    if not config.WEB_TOKEN or not secrets.compare_digest(token, config.WEB_TOKEN):
        raise HTTPException(401, "Token inválido")


# ---------- painel ----------
@app.get("/")
def index():
    return FileResponse("web/index.html")


@app.get("/api/status", dependencies=[Depends(auth)])
def api_status():
    st = engine.status()
    st["config"] = {
        "symbols": config.SYMBOLS, "risk_per_trade": config.RISK_PER_TRADE,
        "max_open": config.MAX_OPEN_TRADES, "max_daily_loss": config.MAX_DAILY_LOSS,
        "threshold": config.SIGNAL_THRESHOLD, "mode": config.EXECUTION_MODE,
    }
    return st


@app.get("/api/signals", dependencies=[Depends(auth)])
def api_signals(limit: int = 50):
    return db.list_signals(limit)


@app.post("/api/signals/{sid}/approve", dependencies=[Depends(auth)])
def api_approve(sid: int):
    return {"message": engine.approve(sid, "web")}


@app.post("/api/signals/{sid}/reject", dependencies=[Depends(auth)])
def api_reject(sid: int):
    return {"message": engine.reject(sid, "web")}


@app.post("/api/trades/{tid}/close", dependencies=[Depends(auth)])
def api_close(tid: int):
    return {"message": trades.close_trade(tid, "web")}


@app.post("/api/trades/close-all", dependencies=[Depends(auth)])
def api_close_all():
    return {"message": trades.close_all("web")}


@app.get("/api/trades", dependencies=[Depends(auth)])
def api_trades(limit: int = 200, status: str | None = None, symbol: str | None = None):
    return db.list_trades(limit, status, symbol)


@app.get("/api/trades/{tid}", dependencies=[Depends(auth)])
def api_trade(tid: int):
    t = db.get_trade(tid)
    if not t:
        raise HTTPException(404, "Trade não encontrado")
    return t


@app.get("/api/stats", dependencies=[Depends(auth)])
def api_stats():
    return trades.stats()


@app.get("/api/corrections", dependencies=[Depends(auth)])
def api_corrections():
    return {"items": db.list_corrections(200), "params": learning.params(), "labels": learning.LABELS}


@app.post("/api/corrections/{cid}/revert", dependencies=[Depends(auth)])
def api_revert(cid: int):
    return {"message": learning.revert(cid, "web")}


@app.post("/api/pause", dependencies=[Depends(auth)])
def api_pause():
    risk.set_paused(True, "web")
    return {"paused": True}


@app.post("/api/resume", dependencies=[Depends(auth)])
def api_resume():
    risk.set_paused(False, "web")
    return {"paused": False}


@app.post("/api/analyze", dependencies=[Depends(auth)])
def api_analyze():
    return {"created": engine.run_cycle()}


@app.get("/api/scores", dependencies=[Depends(auth)])
def api_scores():
    return engine.last_scores()


@app.get("/api/calendar", dependencies=[Depends(auth)])
def api_calendar():
    return cal.next_events(15)


@app.get("/api/log", dependencies=[Depends(auth)])
def api_log(limit: int = 50):
    return db.recent_log(limit)


# ---------- webhook do WhatsApp ----------
@app.get("/webhook")
def wa_verify(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == config.WA_VERIFY_TOKEN:
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403, "Verificação falhou")


def _reply(sender: str, text: str):
    answer = commands.handle(sender, text)
    if answer:
        whatsapp.send_text(sender, answer)


@app.post("/webhook")
async def wa_receive(request: Request, bg: BackgroundTasks):
    raw = await request.body()
    if not whatsapp.valid_signature(raw, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(403, "Assinatura inválida")
    for sender, text in whatsapp.extract_messages(await request.json()):
        bg.add_task(_reply, sender, text)   # responde 200 rápido; processa em seguida
    return {"ok": True}


# ---------- inicialização ----------
def _safe_cycle():
    try:
        engine.run_cycle()
    except Exception as ex:
        db.log(f"Ciclo falhou: {ex}", "ERROR")


def main():
    if not config.WEB_TOKEN:
        raise SystemExit("Defina WEB_TOKEN no .env antes de iniciar.")
    db.init()
    mt5c.connect()
    acc = mt5c.account()
    db.log(f"Conectado ao MT5: conta {acc.get('login')} ({acc.get('trade_mode')}) — DRY_RUN={config.DRY_RUN}")
    paper, why = trades.paper_mode()
    if paper:
        db.log(f"Operando em modo SIMULADO ({why}). Diário e aprendizado funcionam normalmente.", "WARN")
    elif acc.get("trade_mode") == "real":
        db.log(f"ATENÇÃO: conta REAL, modo {config.EXECUTION_MODE} — ordens serão enviadas.", "WARN")

    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(_safe_cycle, "interval", minutes=config.ANALYSIS_INTERVAL_MIN,
                  id="analise", max_instances=1, coalesce=True)
    sched.add_job(engine.expire, "interval", minutes=1, id="expira")
    sched.add_job(trades.monitor, "interval", seconds=30, id="monitor", max_instances=1, coalesce=True)
    sched.add_job(engine.daily_report, "cron", hour=config.DAILY_REPORT_HOUR, minute=2,
                  timezone=config.TIMEZONE, id="resumo")
    sched.start()
    _safe_cycle()  # primeira análise ao iniciar

    modo = "automático" if config.EXECUTION_MODE == "auto" else "confirmação"
    whatsapp.broadcast(f"🤖 ForexBot iniciado — modo {modo}" + (" (simulado)" if paper else "")
                       + ". Envie 'ajuda' para ver os comandos.")
    uvicorn.run(app, host=config.WEB_HOST, port=config.WEB_PORT)


if __name__ == "__main__":
    main()
