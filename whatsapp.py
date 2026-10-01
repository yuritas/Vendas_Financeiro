"""WhatsApp via Meta Cloud API: envio de mensagens e validação do webhook.

Atenção à regra da Meta: mensagens livres só chegam se o número falou com o bot
nas últimas 24h. Fora dessa janela é preciso um *template* aprovado
(WA_TEMPLATE_NAME, com uma variável {{1}} no corpo). Se não houver template,
basta mandar qualquer mensagem ao bot uma vez por dia (ex.: "status").
"""
import hashlib
import hmac

import requests

import config
import db

API = "https://graph.facebook.com/{ver}/{pid}/messages"


def enabled() -> bool:
    return bool(config.WA_TOKEN and config.WA_PHONE_NUMBER_ID)


def _post(payload: dict) -> dict:
    r = requests.post(
        API.format(ver=config.WA_API_VERSION, pid=config.WA_PHONE_NUMBER_ID),
        headers={"Authorization": f"Bearer {config.WA_TOKEN}"},
        json={"messaging_product": "whatsapp", **payload},
        timeout=15,
    )
    data = r.json() if r.content else {}
    if r.status_code >= 400:
        raise RuntimeError(data.get("error", {}).get("message", r.text))
    return data


def send_text(to: str, body: str) -> None:
    if not enabled():
        db.log(f"[WhatsApp desligado] para {to}: {body[:80]}")
        return
    try:
        _post({"to": to, "type": "text", "text": {"body": body[:4000], "preview_url": False}})
    except Exception as ex:
        if config.WA_TEMPLATE_NAME:
            try:
                _post({"to": to, "type": "template", "template": {
                    "name": config.WA_TEMPLATE_NAME, "language": {"code": "pt_BR"},
                    "components": [{"type": "body", "parameters": [{"type": "text", "text": body[:1000]}]}],
                }})
                return
            except Exception as ex2:
                ex = ex2
        db.log(f"Falha ao enviar WhatsApp para {to}: {ex}", "ERROR")


def broadcast(body: str) -> None:
    for n in config.WA_ALLOWED_NUMBERS:
        send_text(n, body)


def valid_signature(raw_body: bytes, header: str | None) -> bool:
    """Confere X-Hub-Signature-256 — garante que a requisição veio da Meta."""
    if not config.WA_APP_SECRET:
        return True  # recomendado configurar em produção
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(config.WA_APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[7:])


def extract_messages(payload: dict) -> list[tuple[str, str]]:
    """Retorna [(numero, texto)] das mensagens de texto recebidas."""
    out = []
    for entry in payload.get("entry", []):
        for ch in entry.get("changes", []):
            for m in ch.get("value", {}).get("messages", []) or []:
                if m.get("type") == "text":
                    out.append((m["from"], m["text"]["body"]))
                elif m.get("type") == "button":
                    out.append((m["from"], m["button"].get("text", "")))
    return out
