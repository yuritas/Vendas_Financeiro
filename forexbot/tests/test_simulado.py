"""Teste de ponta a ponta com MetaTrader 5 SIMULADO (roda em qualquer sistema).

Cobre: análise -> abertura automática -> stop/alvo -> diagnóstico -> correções
do aprendizado -> desfazer correção -> comandos do WhatsApp.
Uso: python tests/test_simulado.py
"""
import os
import sys
import types
from collections import namedtuple
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.update(DB_PATH=":memory:", WA_ALLOWED_NUMBERS="5511999", SIGNAL_THRESHOLD="2.0",
                  DRY_RUN="true", EXECUTION_MODE="auto", MAX_OPEN_TRADES="5", MAX_DAILY_LOSS="50",
                  MACRO_FILE=os.path.join(HERE, "..", "macro.json"), ANTHROPIC_API_KEY="",
                  WA_TOKEN="", LEARN_MIN_TRADES="20")
sys.path.insert(0, os.path.join(HERE, ".."))

# ---------------- MetaTrader5 falso ----------------
PRICE = {"bid": 1.10000}
m = types.ModuleType("MetaTrader5")
for n in ("TIMEFRAME_H1", "TIMEFRAME_H4", "ORDER_TYPE_SELL", "TRADE_ACTION_DEAL", "ORDER_TIME_GTC",
          "ORDER_FILLING_IOC", "ORDER_FILLING_RETURN"):
    setattr(m, n, hash(n) % 1000 + 10)
m.POSITION_TYPE_BUY = m.ORDER_TYPE_BUY = m.ORDER_FILLING_FOK = 0
m.TRADE_RETCODE_DONE = 10009
Acc = namedtuple("Acc", "login server currency balance equity margin_free profit trade_mode")
Info = namedtuple("Info", "digits spread trade_tick_size trade_tick_value volume_step volume_min volume_max filling_mode")
Tick = namedtuple("Tick", "bid ask")
m.initialize = lambda **k: True
m.terminal_info = lambda: object()
m.symbol_select = lambda *a: True
m.last_error = lambda: (0, "")
m.account_info = lambda: Acc(1, "Demo", "USD", 10000.0, 10000.0, 9000.0, 0.0, 0)
m.positions_get = lambda **k: []
m.history_deals_get = lambda *a, **k: []
m.symbol_info = lambda s: Info(5, 12, 0.00001, 1.0, 0.01, 0.01, 100, 1)
m.symbol_info_tick = lambda s: Tick(PRICE["bid"], PRICE["bid"] + 0.00012)


def _rates(s, tf, a, n):
    return [{"high": 1.1010, "low": 1.0990, "close": 1.1000 + (0.001 if i == n - 1 else 0)} for i in range(n)]


m.copy_rates_from_pos = _rates
sys.modules["MetaTrader5"] = m
fp = types.ModuleType("feedparser")
fp.parse = lambda u: types.SimpleNamespace(entries=[])
sys.modules["feedparser"] = fp

# ---------------- calendário falso (formato real do feed) ----------------
from fundamentals import calendar as cal  # noqa: E402

now = datetime.now(timezone.utc)


def ev(title, cc, d, impact, fc):
    return {"title": title, "country": cc, "date": d.isoformat(), "dt": d, "impact": impact, "forecast": fc, "previous": ""}


EVS = [ev("CPI y/y", "AUD", now - timedelta(hours=3), "High", "4.1%"),
       ev("Unemployment Claims", "USD", now - timedelta(hours=2), "Medium", "201K"),
       ev("Cash Rate", "NZD", now + timedelta(minutes=10), "High", "3.00%")]
cal.fetch_events = lambda force=False: EVS

import commands  # noqa: E402
import db  # noqa: E402
import engine  # noqa: E402
import learning  # noqa: E402
import trades  # noqa: E402

db.init()
ok = lambda cond, msg: (print(("✔ " if cond else "✘ ") + msg), None if cond else sys.exit(1))  # noqa: E731

# 1) parsing e surpresas
ok(cal.parse_num("215K") == 215000 and cal.parse_num("-1.2B") == -1.2e9 and cal.parse_num("") is None, "parse de números")
cal.set_actuals([{"key": cal.event_key(EVS[0]), "actual": "4.6%"}, {"key": cal.event_key(EVS[1]), "actual": "230K"}])
sc, _ = cal.scores()
ok(sc["AUD"] > 0 and sc["USD"] < 0, f"surpresas: AUD {sc['AUD']:+.2f}, USD {sc['USD']:+.2f}")

# 2) abertura automática
ids = engine.run_cycle()
opened = [db.get_trade(i) for i in ids]
ok(len(ids) >= 1, f"modo auto abriu {len(ids)} trade(s): " + ", ".join(f"{t['direction']} {t['symbol']}" for t in opened))
ok(all("NZD" not in t["symbol"] for t in opened), "nada aberto em NZD (notícia forte em 10 min)")
t0 = opened[0]
ok(t0["paper"] == 1 and t0["reasons"] and t0["pillars"] and t0["context"]["threshold"], "trade registrado com justificativa, pilares e contexto")
ok(abs(t0["risk_money"] - 50) < 5, f"risco ≈ 0,5% do saldo ({t0['risk_money']})")
ok(engine.run_cycle() == [] or all(db.get_trade(i)["symbol"] not in [t["symbol"] for t in opened] for i in engine.run_cycle()),
   "não duplica operação no mesmo par")

# 3) stop atingido -> diagnóstico -> revisão
def hit(t, where):
    sign = 1 if t["direction"] == "BUY" else -1
    target = t["sl"] if where == "SL" else t["tp"]
    PRICE["bid"] = target - sign * 0.0002 if where == "SL" else target + sign * 0.0002
    if t["direction"] == "SELL":  # vendas usam o ask (bid + spread)
        PRICE["bid"] = (target + 0.0002 if where == "SL" else target - 0.0003) - 0.00012
    trades.monitor()
    PRICE["bid"] = 1.10000
    return db.get_trade(t["id"])

c = hit(t0, "SL")
ok(c["status"] == "closed" and c["exit_reason"] == "SL" and c["r_multiple"] < -0.9, f"stop detectado: {c['r_multiple']:+.2f}R")
cats = [x["code"] for x in c["diagnosis"]["categories"]]
ok("stop_rapido" in cats, f"diagnóstico: {c['diagnosis']['summary']}")

for t in db.list_trades(100, "open"):
    trades.close_trade(t["id"], "teste")

# 4) sequência de perdas reduz risco; vitória restaura
def make_trade(symbol, r_target, direction="BUY"):
    tid, _ = trades.open_trade(symbol, direction, 3.0 if direction == "BUY" else -3.0,
                               {"calendario": 2.5, "noticias": 0.0, "juros": 0.5}, ["teste"], 2.0)
    return hit(db.get_trade(tid), "SL" if r_target < 0 else "TP")

make_trade("EURUSD", -1); make_trade("EURUSD", -1)
ok(learning.params()["risk_mult"] == 0.5, "3 perdas seguidas -> risco reduzido à metade")
t_small = db.get_trade(trades.open_trade("GBPUSD", "BUY", 3, {}, ["teste"], 2.0)[0])
ok(abs(t_small["risk_money"] - 25) < 3, f"novo trade já usa metade do risco ({t_small['risk_money']})")
hit(t_small, "TP")
ok(learning.params()["risk_mult"] == 1.0, "vitória restaura o risco")

# 5) par com expectativa negativa passa a exigir nota maior
for _ in range(9):
    make_trade("USDCAD", -1)
    make_trade("GBPUSD", +1)   # intercala vitórias para não travar no risco
adj = learning.params()["symbol_adj"].get("USDCAD", 0)
ok(adj > 0, f"USDCAD com expectativa negativa -> exigência extra +{adj}")
ok(learning.threshold("USDCAD") > learning.threshold("EURUSD"), "limiar do USDCAD maior que o do EURUSD")

# 6) pesos dos pilares (calendário apoiou vencedores, notícias apoiou perdedores)
for _ in range(6):
    trades.open_trade("AUDUSD", "BUY", 3, {"calendario": 3, "noticias": -1, "juros": 0}, ["teste"], 2.0)
    hit(db.list_trades(1, "open")[0], "TP")
    trades.open_trade("AUDUSD", "BUY", 3, {"calendario": -1, "noticias": 3, "juros": 0}, ["teste"], 2.0)
    hit(db.list_trades(1, "open")[0], "SL")
w = learning.params()["weights"]
ok(w["calendario"] > 1.0 and w["noticias"] < 1.0, f"pesos ajustados: {w}")

corr = db.list_corrections()
ok(len(corr) >= 3, f"{len(corr)} correções registradas com justificativa")
print("   ex.:", corr[0]["justification"])

# 7) desfazer correção
cw = next(c for c in corr if c["kind"] == "weights" and not c["reverted"])
print("  ", learning.revert(cw["id"], "teste"))
ok(learning.params()["weights"][cw["target"]] == cw["old_value"], "correção desfeita voltou ao valor anterior")

# 8) estatísticas e comandos
st = trades.stats()
ok(st["trades"] > 30 and len(st["curve"]) == st["trades"], f"estatísticas: {st['trades']} trades, acerto {st['win_rate']:.0%}, expectativa {st['expectancy_r']:+.2f}R")
ok(commands.handle("5500000", "status") == "", "número não autorizado é ignorado")
for cmd in ("status", "diario", f"trade {c['id']}", "resultado", "correcoes", "abertas", "agenda"):
    out = commands.handle("5511999", cmd)
    ok(bool(out), f"comando '{cmd}' respondeu ({out.splitlines()[0][:60]})")
print(commands.handle("5511999", f"trade {c['id']}"))
engine.daily_report()
print("\nOK — todos os testes passaram")
