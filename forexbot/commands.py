"""Comandos de texto recebidos pelo WhatsApp."""
import unicodedata

import config
import db
import engine
import learning
import risk
import trades
from fundamentals import calendar as cal

HELP = """*Comandos*
status — saldo, resultado do dia e operações abertas
abertas — operações abertas com resultado flutuante
fechar 12 — encerra o trade 12
fechar tudo — encerra todas as operações do robô
diario — últimos trades com resultado e diagnóstico
trade 12 — justificativa e diagnóstico completos do trade 12
resultado — estatísticas acumuladas
correcoes — últimas correções do aprendizado
desfazer 3 — desfaz a correção 3
analise — notas atuais por moeda
agenda — próximas notícias fortes
analisar — roda a análise agora
pausar / retomar — liga/desliga novas entradas
sinais / sim 5 / nao 5 — só no modo confirmação"""


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace("#", " ").split())


def handle(sender: str, text: str) -> str:
    if sender not in config.WA_ALLOWED_NUMBERS:  # lista vazia = ninguém pode comandar
        db.log(f"Mensagem ignorada de número não autorizado: {sender}", "WARN")
        return ""
    parts = _norm(text).split()
    if not parts:
        return HELP
    cmd, args = parts[0], parts[1:]
    num = int(args[0]) if args and args[0].isdigit() else None
    who = f"whatsapp:{sender}"

    try:
        if cmd == "fechar" and args and args[0] == "tudo":
            return trades.close_all(who)
        if cmd == "fechar" and num:
            return trades.close_trade(num, who)
        if cmd in ("sim", "s", "ok", "aprovar") and num:
            return engine.approve(num, who)
        if cmd in ("nao", "n", "descartar") and num:
            return engine.reject(num, who)
        if cmd == "desfazer" and num:
            return learning.revert(num, who)
        if cmd == "status":
            return _status()
        if cmd == "abertas":
            return _open() or "Nenhuma operação aberta."
        if cmd == "diario":
            return _journal()
        if cmd == "trade" and num:
            return _trade(num)
        if cmd in ("resultado", "resultados"):
            return _results()
        if cmd in ("correcoes", "correcao"):
            return _corrections()
        if cmd == "sinais":
            pend = db.list_signals(10, "pending")
            return "\n\n".join(engine.fmt_signal(s) for s in pend) or "Nenhum sinal pendente."
        if cmd == "analise":
            return _scores()
        if cmd == "agenda":
            evs = cal.next_events(8)
            return "\n".join(f"{e['time'][5:16].replace('T', ' ')} UTC {e['currency']} {e['title']} ({e['impact']})"
                             for e in evs) or "Sem eventos relevantes."
        if cmd == "analisar":
            ids = engine.run_cycle()
            what = "operação(ões) aberta(s)" if config.EXECUTION_MODE == "auto" else "sinal(is) criado(s)"
            return f"Análise concluída: {len(ids)} {what}."
        if cmd == "pausar":
            risk.set_paused(True, who)
            return "⏸️ Pausado: nenhuma entrada nova. As abertas continuam com stop e alvo."
        if cmd == "retomar":
            risk.set_paused(False, who)
            return "▶️ Retomado."
    except Exception as ex:
        db.log(f"Erro no comando '{text}': {ex}", "ERROR")
        return f"Erro: {ex}"
    return HELP


def _status() -> str:
    st = engine.status()
    a = st["account"]
    if not a:
        return "Sem conexão com o MT5."
    mode = "automático" if st["mode"] == "auto" else "confirmação"
    lines = [
        f"*Conta {a['login']}* ({a['trade_mode']}) — modo {mode}" + (" — *SIMULADO*" if st["paper"] else ""),
        f"Saldo {a['balance']:.2f} | Patrimônio {a['equity']:.2f} {a['currency']}",
        f"Resultado do dia (robô): {st['daily_pnl']:+.2f}",
        "⏸️ PAUSADO" if st["paused"] else "▶️ Ativo",
    ]
    o = _open()
    if o:
        lines.append(o)
    return "\n".join(lines)


def _open() -> str:
    return "\n".join(f"• #{t['id']} {t['direction']} {t['symbol']} {t['volume']} → {t['floating']:+.2f} "
                     f"({t['floating_r']:+.2f}R)" for t in trades.open_with_floating())


def _journal() -> str:
    ts = db.list_trades(8, "closed")
    if not ts:
        return "Nenhuma operação encerrada ainda."
    out = []
    for t in ts:
        cats = ", ".join(c["label"] for c in (t.get("diagnosis") or {}).get("categories", [])[:2]) or "—"
        out.append(f"#{t['id']} {t['direction']} {t['symbol']} {t['r_multiple']:+.2f}R ({t['exit_reason']}) — {cats}")
    return "*Diário*\n" + "\n".join(out) + "\n\nDetalhes: *trade <n>*"


def _trade(tid: int) -> str:
    t = db.get_trade(tid)
    if not t:
        return f"Trade #{tid} não existe."
    d = t.get("diagnosis") or {}
    lines = [f"*Trade #{t['id']}* {t['direction']} {t['symbol']} {t['volume']} lote"
             + (" (simulado)" if t["paper"] else ""),
             f"Entrada {t['entry']} | SL {t['sl']} | TP {t['tp']} | nota {t['score']:+.1f}",
             "*Justificativa:*"] + [f"• {r}" for r in (t.get("reasons") or [])[:6]]
    if t["status"] == "closed":
        lines += [f"*Resultado:* {t['profit']:+.2f} ({t['r_multiple']:+.2f}R) — {t['exit_reason']}",
                  f"*Diagnóstico:* {d.get('summary', '-')}"]
        if d.get("analise"):
            lines.append(f"*Análise:* {d['analise']}")
        if d.get("licao"):
            lines.append(f"*Lição:* {d['licao']}")
    else:
        lines.append("Em aberto.")
    return "\n".join(lines)


def _results() -> str:
    s = trades.stats()
    if not s["trades"]:
        return "Ainda não há operações encerradas."
    lines = [f"*Resultado acumulado* — {s['trades']} trades",
             f"Acerto {s['win_rate']:.0%} | expectativa {s['expectancy_r']:+.2f}R | "
             f"fator de lucro {s['profit_factor'] or '—'}",
             f"Lucro {s['profit']:+.2f} | drawdown máx {s['max_drawdown']:.2f}"]
    if s["loss_causes"]:
        lines.append("Principais causas de perda: " + ", ".join(f"{k} ({v})" for k, v in list(s["loss_causes"].items())[:3]))
    if s["trades"] < config.LEARN_MIN_TRADES:
        lines.append(f"Aprendizado de pesos começa com {config.LEARN_MIN_TRADES} trades.")
    return "\n".join(lines)


def _corrections() -> str:
    cs = db.list_corrections(6)
    if not cs:
        return "Nenhuma correção aplicada ainda."
    return "\n\n".join(
        f"#{c['id']} {learning.LABELS.get(c['kind'], c['kind'])} [{c['target']}]: {c['old_value']} → {c['new_value']}"
        f"{' (desfeita)' if c['reverted'] else ''}\n{c['justification']}" for c in cs)


def _scores() -> str:
    last = engine.last_scores()
    if not last["scores"]:
        return "Ainda não houve análise. Envie 'analisar'."
    rows = sorted(last["scores"]["total"].items(), key=lambda kv: -kv[1])
    return f"*Notas por moeda* ({last['at'][11:16]} UTC)\n" + "\n".join(f"{c}: {v:+.1f}" for c, v in rows)
