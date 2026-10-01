"""MetaTrader 5, feedparser e calendário falsos — compartilhados pelos testes.

Uso (antes de importar qualquer módulo do projeto):
    import fakes
    fakes.install(WEB_TOKEN="x", ...)   # variáveis de ambiente extras/sobrescritas
"""
import os
import sys
import types
from collections import namedtuple
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))

PRICE = {"bid": 1.10000}

ENV = dict(DB_PATH=":memory:", WA_ALLOWED_NUMBERS="5511999", SIGNAL_THRESHOLD="2.0",
           DRY_RUN="true", EXECUTION_MODE="auto", MAX_OPEN_TRADES="5", MAX_DAILY_LOSS="50",
           MACRO_FILE=os.path.join(ROOT, "macro.json"), ANTHROPIC_API_KEY="",
           WA_TOKEN="", LEARN_MIN_TRADES="20")


def _fake_mt5() -> types.ModuleType:
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
    m.copy_rates_from_pos = lambda s, tf, a, n: [
        {"high": 1.1010, "low": 1.0990, "close": 1.1000 + (0.001 if i == n - 1 else 0)} for i in range(n)]
    return m


def install(**env) -> None:
    """Define o ambiente de teste e troca as dependências externas por versões falsas."""
    os.environ.update({**ENV, **env})
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    sys.modules["MetaTrader5"] = _fake_mt5()
    fp = types.ModuleType("feedparser")
    fp.parse = lambda u: types.SimpleNamespace(entries=[])
    sys.modules["feedparser"] = fp


def ev(title, cc, d, impact, fc):
    """Evento no formato do feed real da Forex Factory."""
    return {"title": title, "country": cc, "date": d.isoformat(), "dt": d, "impact": impact, "forecast": fc, "previous": ""}


def install_calendar() -> list[dict]:
    """Troca o feed do calendário por eventos fixos (AUD forte, USD fraco, NZD com notícia em 10 min).
    Retorna a lista de eventos. Só chame depois de install()."""
    from fundamentals import calendar as cal

    now = datetime.now(timezone.utc)
    evs = [ev("CPI y/y", "AUD", now - timedelta(hours=3), "High", "4.1%"),
           ev("Unemployment Claims", "USD", now - timedelta(hours=2), "Medium", "201K"),
           ev("Cash Rate", "NZD", now + timedelta(minutes=10), "High", "3.00%")]
    cal.fetch_events = lambda force=False: evs
    return evs


def set_surprises(evs: list[dict]) -> None:
    """Resultados acima/abaixo do previsto: AUD positivo, USD negativo."""
    from fundamentals import calendar as cal

    cal.set_actuals([{"key": cal.event_key(evs[0]), "actual": "4.6%"},
                     {"key": cal.event_key(evs[1]), "actual": "230K"}])
