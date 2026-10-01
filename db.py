"""Persistência simples em SQLite: sinais, log de eventos e chave/valor."""
import json
import sqlite3
import threading
from datetime import datetime, timezone

import config

_lock = threading.Lock()
_c = sqlite3.connect(config.DB_PATH, check_same_thread=False)
_c.row_factory = sqlite3.Row


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init() -> None:
    with _lock:
        _c.executescript(
            """
            CREATE TABLE IF NOT EXISTS signals(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT, expires_at TEXT,
                symbol TEXT, direction TEXT, score REAL,
                entry REAL, sl REAL, tp REAL, volume REAL,
                reasons TEXT,
                status TEXT,            -- pending|approved|rejected|expired|executed|failed
                decided_by TEXT, decided_at TEXT,
                ticket INTEGER, error TEXT
            );
            CREATE TABLE IF NOT EXISTS log(
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, level TEXT, msg TEXT
            );
            CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
            CREATE TABLE IF NOT EXISTS trades(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER, ticket INTEGER, paper INTEGER,
                symbol TEXT, direction TEXT, volume REAL,
                entry REAL, sl REAL, tp REAL, risk_money REAL, atr REAL, spread REAL,
                opened_at TEXT, closed_at TEXT, exit_price REAL,
                profit REAL, r_multiple REAL, exit_reason TEXT,
                score REAL, pillars TEXT,       -- contribuição de cada pilar ao par na entrada
                reasons TEXT,                   -- justificativa da entrada
                context TEXT,                   -- parâmetros vigentes (pesos, limiar, risco)
                status TEXT,                    -- open | closed
                diagnosis TEXT                  -- json: categorias, texto, sugestão
            );
            CREATE TABLE IF NOT EXISTS corrections(
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT,
                kind TEXT, target TEXT, old_value TEXT, new_value TEXT,
                justification TEXT, evidence TEXT, reverted INTEGER DEFAULT 0
            );
            """
        )
        _c.commit()


def _row(r):
    if r is None:
        return None
    d = dict(r)
    if d.get("reasons"):
        d["reasons"] = json.loads(d["reasons"])
    return d


def add_signal(**f) -> int:
    f.setdefault("created_at", now_iso())
    f.setdefault("status", "pending")
    f["reasons"] = json.dumps(f.get("reasons", []), ensure_ascii=False)
    cols = ",".join(f)
    q = ",".join("?" for _ in f)
    with _lock:
        cur = _c.execute(f"INSERT INTO signals({cols}) VALUES({q})", tuple(f.values()))
        _c.commit()
        return cur.lastrowid


def update_signal(sid: int, **f) -> None:
    sets = ",".join(f"{k}=?" for k in f)
    with _lock:
        _c.execute(f"UPDATE signals SET {sets} WHERE id=?", (*f.values(), sid))
        _c.commit()


def get_signal(sid: int):
    with _lock:
        return _row(_c.execute("SELECT * FROM signals WHERE id=?", (sid,)).fetchone())


def list_signals(limit: int = 50, status: str | None = None):
    with _lock:
        if status:
            rows = _c.execute(
                "SELECT * FROM signals WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit)
            ).fetchall()
        else:
            rows = _c.execute("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [_row(r) for r in rows]


def has_pending(symbol: str) -> bool:
    with _lock:
        r = _c.execute(
            "SELECT 1 FROM signals WHERE symbol=? AND status='pending' LIMIT 1", (symbol,)
        ).fetchone()
    return r is not None


def expire_pending() -> list[int]:
    now = now_iso()
    with _lock:
        rows = _c.execute(
            "SELECT id FROM signals WHERE status='pending' AND expires_at < ?", (now,)
        ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            _c.execute(
                f"UPDATE signals SET status='expired' WHERE id IN ({','.join('?' * len(ids))})", ids
            )
            _c.commit()
    return ids


def log(msg: str, level: str = "INFO") -> None:
    print(f"[{level}] {msg}", flush=True)
    with _lock:
        _c.execute("INSERT INTO log(ts,level,msg) VALUES(?,?,?)", (now_iso(), level, msg))
        _c.commit()


def recent_log(limit: int = 50):
    with _lock:
        rows = _c.execute("SELECT * FROM log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_kv(k: str, default=None):
    with _lock:
        r = _c.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return json.loads(r["v"]) if r else default


def set_kv(k: str, v) -> None:
    with _lock:
        _c.execute("INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)", (k, json.dumps(v)))
        _c.commit()


# ---------------- diário de operações ----------------
_JSON_TRADE = ("pillars", "reasons", "context", "diagnosis")


def _trade(r):
    if r is None:
        return None
    d = dict(r)
    for k in _JSON_TRADE:
        if d.get(k):
            d[k] = json.loads(d[k])
    return d


def add_trade(**f) -> int:
    f.setdefault("opened_at", now_iso())
    f.setdefault("status", "open")
    for k in _JSON_TRADE:
        if k in f and not isinstance(f[k], str):
            f[k] = json.dumps(f[k], ensure_ascii=False)
    cols, q = ",".join(f), ",".join("?" for _ in f)
    with _lock:
        cur = _c.execute(f"INSERT INTO trades({cols}) VALUES({q})", tuple(f.values()))
        _c.commit()
        return cur.lastrowid


def update_trade(tid: int, **f) -> None:
    for k in _JSON_TRADE:
        if k in f and not isinstance(f[k], str):
            f[k] = json.dumps(f[k], ensure_ascii=False)
    sets = ",".join(f"{k}=?" for k in f)
    with _lock:
        _c.execute(f"UPDATE trades SET {sets} WHERE id=?", (*f.values(), tid))
        _c.commit()


def get_trade(tid: int):
    with _lock:
        return _trade(_c.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone())


def list_trades(limit: int = 100, status: str | None = None, symbol: str | None = None):
    q, args = "SELECT * FROM trades WHERE 1=1", []
    if status:
        q += " AND status=?"; args.append(status)
    if symbol:
        q += " AND symbol=?"; args.append(symbol)
    q += " ORDER BY id DESC LIMIT ?"; args.append(limit)
    with _lock:
        rows = _c.execute(q, args).fetchall()
    return [_trade(r) for r in rows]


def closed_trades_chrono(limit: int):
    """Últimos `limit` trades fechados, do mais antigo para o mais novo."""
    with _lock:
        rows = _c.execute(
            "SELECT * FROM trades WHERE status='closed' ORDER BY closed_at DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_trade(r) for r in reversed(rows)]


# ---------------- correções do aprendizado ----------------
def add_correction(kind, target, old, new, justification, evidence) -> int:
    with _lock:
        cur = _c.execute(
            "INSERT INTO corrections(ts,kind,target,old_value,new_value,justification,evidence) "
            "VALUES(?,?,?,?,?,?,?)",
            (now_iso(), kind, target, json.dumps(old), json.dumps(new), justification,
             json.dumps(evidence, ensure_ascii=False)),
        )
        _c.commit()
        return cur.lastrowid


def list_corrections(limit: int = 100):
    with _lock:
        rows = _c.execute("SELECT * FROM corrections ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("old_value", "new_value", "evidence"):
            d[k] = json.loads(d[k]) if d[k] else None
        out.append(d)
    return out


def get_correction(cid: int):
    for c in list_corrections(10**6):
        if c["id"] == cid:
            return c
    return None


def mark_reverted(cid: int) -> None:
    with _lock:
        _c.execute("UPDATE corrections SET reverted=1 WHERE id=?", (cid,))
        _c.commit()
