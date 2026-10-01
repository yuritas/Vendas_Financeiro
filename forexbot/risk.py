"""Regras de risco checadas antes de qualquer abertura."""
import config
import db
import mt5_client as mt5c


def is_paused() -> bool:
    return bool(db.get_kv("paused", False))


def set_paused(v: bool, reason: str = "") -> None:
    db.set_kv("paused", v)
    db.log(("PAUSADO" if v else "RETOMADO") + (f": {reason}" if reason else ""), "WARN" if v else "INFO")


def can_open(symbol: str) -> tuple[bool, str]:
    import trades  # import tardio: trades importa módulos que dependem deste
    import whatsapp

    if is_paused():
        return False, "sistema pausado"
    acc = mt5c.account()
    if not acc:
        return False, "sem conexão com a conta"
    open_trades = db.list_trades(1000, "open")
    if len(open_trades) >= config.MAX_OPEN_TRADES:
        return False, f"limite de {config.MAX_OPEN_TRADES} operações abertas"
    if any(t["symbol"] == symbol for t in open_trades):
        return False, f"já existe operação em {symbol}"
    pnl = trades.daily_pnl()
    limit = -acc["balance"] * config.MAX_DAILY_LOSS / 100
    if pnl <= limit:
        set_paused(True, f"perda diária {pnl:.2f} atingiu o limite {limit:.2f}")
        whatsapp.broadcast(f"⛔ Limite de perda diária atingido ({pnl:.2f}). Sistema pausado — "
                           f"envie *retomar* quando quiser voltar.")
        return False, "limite de perda diária atingido"
    if mt5c.spread_points(symbol) > config.MAX_SPREAD_POINTS:
        return False, f"spread alto em {symbol}"
    return True, "ok"
