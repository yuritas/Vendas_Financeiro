"""Camada fina sobre o pacote MetaTrader5 (só funciona no Windows).

A API do MT5 não é thread-safe, então toda chamada passa por um lock.
"""
import math
import threading
from datetime import datetime, timezone
from functools import wraps

import MetaTrader5 as mt5

import config

_lock = threading.RLock()


def locked(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        with _lock:
            _ensure()
            return fn(*a, **kw)
    return wrapper


def connect() -> None:
    kw = {}
    if config.MT5_PATH:
        kw["path"] = config.MT5_PATH
    if config.MT5_LOGIN:
        kw.update(login=config.MT5_LOGIN, password=config.MT5_PASSWORD, server=config.MT5_SERVER)
    if not mt5.initialize(**kw):
        raise RuntimeError(f"Falha ao conectar no MT5: {mt5.last_error()}")
    for s in config.SYMBOLS:
        mt5.symbol_select(sym(s), True)


def _ensure() -> None:
    if mt5.terminal_info() is None:
        connect()


def sym(symbol: str) -> str:
    return symbol + config.SYMBOL_SUFFIX


@locked
def account() -> dict:
    a = mt5.account_info()
    if a is None:
        return {}
    return {
        "login": a.login, "server": a.server, "currency": a.currency,
        "balance": a.balance, "equity": a.equity, "margin_free": a.margin_free,
        "profit": a.profit, "trade_mode": "demo" if a.trade_mode == 0 else "real",
    }


@locked
def positions(only_bot: bool = False) -> list[dict]:
    out = []
    for p in mt5.positions_get() or []:
        if only_bot and p.magic != config.MAGIC:
            continue
        out.append({
            "ticket": p.ticket, "symbol": p.symbol,
            "type": "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
            "volume": p.volume, "price_open": p.price_open, "price_current": p.price_current,
            "sl": p.sl, "tp": p.tp, "profit": p.profit, "magic": p.magic,
            "bot": p.magic == config.MAGIC,
        })
    return out


@locked
def spread_points(symbol: str) -> int:
    info = mt5.symbol_info(sym(symbol))
    return int(info.spread) if info else 10**6


@locked
def atr(symbol: str, period: int | None = None, timeframe=mt5.TIMEFRAME_H1) -> float:
    period = period or config.ATR_PERIOD
    rates = mt5.copy_rates_from_pos(sym(symbol), timeframe, 0, period + 1)
    if rates is None or len(rates) < period + 1:
        raise RuntimeError(f"Sem histórico suficiente para ATR de {symbol}")
    trs = []
    for i in range(1, len(rates)):
        h, l, pc = rates[i]["high"], rates[i]["low"], rates[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs)


@locked
def price(symbol: str, direction: str) -> float:
    t = mt5.symbol_info_tick(sym(symbol))
    if t is None:
        raise RuntimeError(f"Sem cotação para {symbol}")
    return t.ask if direction == "BUY" else t.bid


@locked
def digits(symbol: str) -> int:
    return mt5.symbol_info(sym(symbol)).digits


@locked
def calc_volume(symbol: str, sl_distance: float, risk_pct: float) -> float:
    """Lote para que a perda até o stop seja ~risk_pct% do saldo."""
    info = mt5.symbol_info(sym(symbol))
    acc = mt5.account_info()
    risk_money = acc.balance * risk_pct / 100
    loss_per_lot = sl_distance / info.trade_tick_size * info.trade_tick_value
    if loss_per_lot <= 0:
        raise RuntimeError("Valor de tick inválido")
    vol = risk_money / loss_per_lot
    step = info.volume_step
    vol = math.floor(vol / step) * step
    vol = max(info.volume_min, min(vol, info.volume_max))
    return round(vol, max(0, -int(math.floor(math.log10(step)))))


def _filling(info) -> int:
    # filling_mode é um bitmask: 1 = FOK, 2 = IOC
    if info.filling_mode & 1:
        return mt5.ORDER_FILLING_FOK
    if info.filling_mode & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


@locked
def send_market(symbol: str, direction: str, volume: float, sl: float, tp: float, comment: str) -> int:
    s = sym(symbol)
    info = mt5.symbol_info(s)
    px = price(symbol, direction)
    req = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": s, "volume": volume,
        "type": mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": px, "sl": round(sl, info.digits), "tp": round(tp, info.digits),
        "deviation": 20, "magic": config.MAGIC, "comment": comment[:31],
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": _filling(info),
    }
    r = mt5.order_send(req)
    if r is None or r.retcode != mt5.TRADE_RETCODE_DONE:
        raise RuntimeError(f"Ordem recusada: {getattr(r, 'retcode', None)} {getattr(r, 'comment', mt5.last_error())}")
    return r.order


@locked
def close_position(ticket: int) -> None:
    ps = mt5.positions_get(ticket=ticket)
    if not ps:
        raise RuntimeError(f"Posição {ticket} não encontrada")
    p = ps[0]
    info = mt5.symbol_info(p.symbol)
    t = mt5.symbol_info_tick(p.symbol)
    is_buy = p.type == mt5.POSITION_TYPE_BUY
    req = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": p.volume,
        "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
        "position": p.ticket, "price": t.bid if is_buy else t.ask,
        "deviation": 20, "magic": config.MAGIC, "comment": "close",
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": _filling(info),
    }
    r = mt5.order_send(req)
    if r is None or r.retcode != mt5.TRADE_RETCODE_DONE:
        raise RuntimeError(f"Falha ao fechar: {getattr(r, 'retcode', None)} {getattr(r, 'comment', mt5.last_error())}")


@locked
def daily_pnl() -> float:
    """Resultado realizado hoje (UTC) pelas ordens do robô + flutuante das abertas."""
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(start, datetime.now(timezone.utc)) or []
    realized = sum(d.profit + d.commission + d.swap for d in deals if d.magic == config.MAGIC)
    floating = sum(p.profit for p in (mt5.positions_get() or []) if p.magic == config.MAGIC)
    return realized + floating


@locked
def tick(symbol: str) -> tuple[float, float]:
    t = mt5.symbol_info_tick(sym(symbol))
    if t is None:
        raise RuntimeError(f"Sem cotação para {symbol}")
    return t.bid, t.ask


@locked
def money_for_distance(symbol: str, distance: float, volume: float) -> float:
    """Quanto vale (na moeda da conta) um movimento de `distance` com `volume` lotes."""
    info = mt5.symbol_info(sym(symbol))
    return distance / info.trade_tick_size * info.trade_tick_value * volume


@locked
def is_open(ticket: int) -> bool:
    return bool(mt5.positions_get(ticket=ticket))


# DEAL_ENTRY_OUT = 1, DEAL_ENTRY_OUT_BY = 3 ; DEAL_REASON_SL = 4, TP = 5, SO = 6, EXPERT = 3
_REASONS = {4: "SL", 5: "TP", 6: "STOP_OUT", 3: "ROBO"}


@locked
def closed_info(ticket: int) -> dict | None:
    """Dados de fechamento de uma posição (None se ainda aberta/sem histórico)."""
    deals = mt5.history_deals_get(position=ticket) or []
    outs = [d for d in deals if d.entry in (1, 3)]
    if not outs:
        return None
    last = outs[-1]
    return {
        "exit_price": last.price,
        "profit": sum(d.profit + d.commission + d.swap for d in deals),
        "exit_reason": _REASONS.get(last.reason, "MANUAL"),
        "closed_at": datetime.fromtimestamp(last.time, timezone.utc).isoformat(timespec="seconds"),
    }


@locked
def trend(symbol: str, period: int = 50, timeframe=mt5.TIMEFRAME_H4) -> int:
    """+1 se o preço está acima da média de `period` candles H4, -1 se abaixo."""
    rates = mt5.copy_rates_from_pos(sym(symbol), timeframe, 0, period)
    if rates is None or len(rates) < period:
        return 0
    closes = [float(r["close"]) for r in rates]
    sma = sum(closes) / len(closes)
    return 1 if closes[-1] > sma else -1 if closes[-1] < sma else 0
