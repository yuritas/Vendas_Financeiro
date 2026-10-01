"""Testes da API FastAPI (painel + webhook do WhatsApp) com fastapi.testclient.

Usa o mesmo MetaTrader 5 falso do teste simulado — roda em qualquer sistema.
Uso: python tests/test_api.py      (precisa de fastapi e httpx)
"""
import hashlib
import hmac
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fakes  # noqa: E402

TOKEN, VERIFY, SECRET = "token-teste", "verifica-teste", "segredo-teste"
fakes.install(WEB_TOKEN=TOKEN, WA_VERIFY_TOKEN=VERIFY, WA_APP_SECRET=SECRET)
EVS = fakes.install_calendar()

os.chdir(os.path.expanduser("~"))  # o painel não pode depender da pasta de onde o bot é iniciado

from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
import db  # noqa: E402
import learning  # noqa: E402
import main  # noqa: E402
import whatsapp  # noqa: E402

db.init()
fakes.set_surprises(EVS)
client = TestClient(main.app)
H = {"Authorization": f"Bearer {TOKEN}"}
ok = lambda cond, msg: (print(("✔ " if cond else "✘ ") + msg), None if cond else sys.exit(1))  # noqa: E731

sent = []  # respostas que iriam para o WhatsApp
whatsapp.send_text = lambda to, body: sent.append((to, body))


def get(path, **kw):
    return client.get(path, headers=H, **kw)


def post(path, **kw):
    return client.post(path, headers=H, **kw)


# 1) painel
r = client.get("/")
ok(r.status_code == 200 and "<html" in r.text.lower(), "GET / serve o painel (mesmo fora da pasta do projeto)")

# 2) autenticação
GETS = ["/api/status", "/api/signals", "/api/trades", "/api/stats", "/api/corrections",
        "/api/scores", "/api/calendar", "/api/log"]
POSTS = ["/api/pause", "/api/resume", "/api/analyze", "/api/trades/close-all",
         "/api/signals/1/approve", "/api/signals/1/reject", "/api/trades/1/close", "/api/corrections/1/revert"]
ok(all(client.get(p).status_code == 401 for p in GETS), "GET sem token -> 401 em todas as rotas")
ok(all(client.post(p).status_code == 401 for p in POSTS), "POST sem token -> 401 em todas as rotas")
bad = {"Authorization": "Bearer errado"}
ok(all(client.get(p, headers=bad).status_code == 401 for p in GETS), "token errado -> 401")
ok(client.get("/api/status", headers={"Authorization": TOKEN}).status_code == 200, "aceita token sem o prefixo 'Bearer'")
config.WEB_TOKEN = ""
ok(client.get("/api/status", headers={"Authorization": "Bearer "}).status_code == 401, "WEB_TOKEN vazio bloqueia tudo")
config.WEB_TOKEN = TOKEN
ok(all(get(p).status_code == 200 for p in GETS), "com token, todas as rotas GET respondem 200")

# 3) status
st = get("/api/status").json()
ok(st["account"]["login"] == 1 and st["paper"] and st["dry_run"] and not st["paused"], "status: conta, modo simulado, não pausado")
ok(st["config"]["mode"] == "auto" and st["config"]["symbols"] == config.SYMBOLS and st["config"]["threshold"] == 2.0,
   "status: configuração exposta ao painel")

# 4) análise em modo automático
ids = post("/api/analyze").json()["created"]
ok(len(ids) >= 1, f"POST /api/analyze abriu {len(ids)} trade(s)")
trades_ = get("/api/trades").json()
ok({t["id"] for t in trades_} >= set(ids) and all(t["status"] == "open" for t in trades_), "GET /api/trades lista os abertos")
ok(all(t["symbol"] == trades_[0]["symbol"] for t in get("/api/trades", params={"symbol": trades_[0]["symbol"]}).json()),
   "filtro por símbolo")
ok(get("/api/trades", params={"status": "closed"}).json() == [], "filtro por status")
t = get(f"/api/trades/{ids[0]}").json()
ok(t["id"] == ids[0] and t["reasons"] and t["pillars"] and t["context"], "GET /api/trades/{id} traz justificativa e contexto")
ok(get("/api/trades/99999").status_code == 404, "trade inexistente -> 404")
ok(get("/api/scores").json()["scores"]["total"]["AUD"] > 0, "GET /api/scores com a última análise")
ok(any(e["currency"] == "NZD" for e in get("/api/calendar").json()), "GET /api/calendar com os próximos eventos")
ok(len(get("/api/status").json()["open_trades"]) == len(ids), "status mostra as operações abertas")

# 5) encerramento
msg = post(f"/api/trades/{ids[0]}/close").json()["message"]
ok("encerrado" in msg and get(f"/api/trades/{ids[0]}").json()["status"] == "closed", f"fechar trade: {msg}")
ok("já está encerrado" in post(f"/api/trades/{ids[0]}/close").json()["message"], "fechar de novo não duplica")
ok("não existe" in post("/api/trades/99999/close").json()["message"], "fechar trade inexistente")
post("/api/trades/close-all")
ok(get("/api/trades", params={"status": "open"}).json() == [], "close-all encerra tudo")
ok(post("/api/trades/close-all").json()["message"] == "Nenhuma operação aberta.", "close-all sem operações")
s = get("/api/stats").json()
ok(s["trades"] == len(ids), f"GET /api/stats: {s['trades']} trade(s) encerrado(s)")

# 6) pausa
ok(post("/api/pause").json() == {"paused": True} and get("/api/status").json()["paused"], "pausar")
ok(post("/api/analyze").json()["created"] == [], "pausado: análise não abre nada")
ok(post("/api/resume").json() == {"paused": False} and not get("/api/status").json()["paused"], "retomar")

# 7) modo confirmação: sinais, aprovar e descartar
config.EXECUTION_MODE = "confirm"
sids = post("/api/analyze").json()["created"]
ok(len(sids) >= 2, f"modo confirmação criou {len(sids)} sinal(is)")
pend = get("/api/signals").json()
ok({x["id"] for x in pend} >= set(sids) and all(x["status"] == "pending" for x in pend), "GET /api/signals lista pendentes")
msg = post(f"/api/signals/{sids[0]}/approve").json()["message"]
ok("executado" in msg and get("/api/trades", params={"status": "open"}).json(), f"aprovar: {msg}")
ok("descartado" in post(f"/api/signals/{sids[1]}/reject").json()["message"], "descartar sinal")
ok("não pode ser executado" in post(f"/api/signals/{sids[1]}/approve").json()["message"], "aprovar sinal descartado é recusado")
ok("já está" in post(f"/api/signals/{sids[0]}/reject").json()["message"], "descartar sinal executado é recusado")
ok("não existe" in post("/api/signals/99999/approve").json()["message"], "sinal inexistente")
config.EXECUTION_MODE = "auto"
post("/api/trades/close-all")

# 8) correções
c = learning.apply("threshold_adj", "", 0.5, "teste da API", {"n": 1}, 1)
body = get("/api/corrections").json()
ok(any(x["id"] == c["id"] for x in body["items"]) and "labels" in body and "weights" in body["params"],
   "GET /api/corrections traz correções, parâmetros e rótulos")
msg = post(f"/api/corrections/{c['id']}/revert").json()["message"]
ok("desfeita" in msg and learning.params()["threshold_adj"] == 0.0, f"desfazer: {msg}")
ok("já foi desfeita" in post(f"/api/corrections/{c['id']}/revert").json()["message"], "desfazer de novo é recusado")

# 9) log
log = get("/api/log", params={"limit": 5}).json()
ok(len(log) == 5 and all("msg" in x for x in log), "GET /api/log respeita o limite")

# 10) webhook — verificação da Meta
q = {"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "12345"}
r = client.get("/webhook", params=q)
ok(r.status_code == 200 and r.text == "12345", "verificação do webhook devolve o challenge")
ok(client.get("/webhook", params={**q, "hub.verify_token": "x"}).status_code == 403, "verify_token errado -> 403")
ok(client.get("/webhook", params={**q, "hub.mode": "unsubscribe"}).status_code == 403, "hub.mode errado -> 403")
config.WA_VERIFY_TOKEN = ""
ok(client.get("/webhook", params={**q, "hub.verify_token": ""}).status_code == 403,
   "WA_VERIFY_TOKEN vazio não aceita verify_token vazio")
config.WA_VERIFY_TOKEN = VERIFY


# 11) webhook — mensagens recebidas
def wa_payload(sender, text):
    return {"entry": [{"changes": [{"value": {"messages": [
        {"from": sender, "type": "text", "text": {"body": text}}]}}]}]}


def wa_post(payload, sign=True, secret=SECRET):
    raw = json.dumps(payload).encode()
    h = {"Content-Type": "application/json"}
    if sign:
        h["X-Hub-Signature-256"] = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/webhook", content=raw, headers=h)


sent.clear()
r = wa_post(wa_payload("5511999", "status"))
ok(r.status_code == 200 and r.json() == {"ok": True}, "webhook assinado -> 200")
ok(len(sent) == 1 and sent[0][0] == "5511999" and sent[0][1], f"comando respondido: {sent[0][1].splitlines()[0][:60]}")
sent.clear()
ok(wa_post(wa_payload("5511999", "status"), sign=False).status_code == 403, "sem assinatura -> 403")
ok(wa_post(wa_payload("5511999", "status"), secret="outro").status_code == 403, "assinatura errada -> 403")
ok(sent == [], "requisição recusada não executa comando")
ok(wa_post(wa_payload("5500000", "status")).status_code == 200 and sent == [], "número não autorizado é ignorado")
ok(wa_post({"entry": [{"changes": [{"value": {"statuses": [{"id": "x"}]}}]}]}).status_code == 200 and sent == [],
   "notificação de status (sem mensagem) é aceita e ignorada")
wa_post(wa_payload("5511999", "pausar"))
ok(get("/api/status").json()["paused"], "comando 'pausar' pelo WhatsApp reflete no painel")
wa_post(wa_payload("5511999", "retomar"))

print("\nOK — todos os testes da API passaram")
