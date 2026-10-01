# CLAUDE.md — contexto do projeto ForexBot

Este arquivo passa para o Claude Code o contexto da conversa em que o projeto foi criado
(no app do Claude, em 01/10/2026). Leia antes de mexer no código.

## Objetivo
Sistema de trades em **forex** com **análise fundamentalista**, em **Python + MetaTrader 5**,
com **execução automática** das ordens e acompanhamento por **WhatsApp** e **página web**.
A web documenta todas as entradas com justificativa, mostra resultados, diagnósticos e
correções — e o sistema **aprende com os erros**.

## Decisões já tomadas pelo usuário
- Execução: **automática** (`EXECUTION_MODE=auto`); o modo `confirm` (aprovar com `SIM <id>`) existe como alternativa.
- WhatsApp: **Meta Cloud API** (oficial).
- Fundamentos: **calendário econômico + notícias com IA (Claude) + juros/macro** — os três pilares.
- Servidor: **VPS Windows** (a lib `MetaTrader5` só roda no Windows, com o terminal aberto).
- Idioma de toda a interface, mensagens e documentação: **português do Brasil**.

## Decisões de projeto (e por quê)
- **Começa em modo simulado** (`DRY_RUN=true`): usa preços reais do MT5, verifica SL/TP a cada 30 s
  e alimenta diário/diagnóstico/aprendizado sem enviar ordens. Serve para acumular histórico.
- **Trava para conta real:** conta real + modo auto + `DRY_RUN=false` continua simulando até
  `ALLOW_REAL_AUTO=true`. Não remover essa trava.
- **Aprendizado só por regras estatísticas** (learning.py), com amostra mínima, passos pequenos,
  limites e cooldown. Cada correção é gravada com justificativa + evidência e pode ser desfeita.
  **Nenhuma correção aumenta o risco por trade.** Sugestões da IA no diagnóstico são só texto —
  não alteram parâmetros. Manter esses princípios ao evoluir.
- Regras por padrão de diagnóstico só contam perdas **depois** da última mudança daquele
  parâmetro (evita reagir duas vezes à mesma evidência).
- O feed da Forex Factory (`ff_calendar_thisweek.json`) **não traz o resultado ("actual")**;
  a IA extrai os resultados das manchetes (news.py → calendar.set_actuals). Sem `ANTHROPIC_API_KEY`,
  só o pilar de juros funciona. O feed limita requisições: cache de 30 min.
- `macro.json` é **manual** e os valores atuais são **exemplos** — o usuário precisa atualizar.
- Webhook do WhatsApp exige HTTPS: sugestão foi **Cloudflare Tunnel**, com `WEB_HOST=127.0.0.1`.
- Mensagens livres da Meta só valem na janela de 24h; fora dela usa template (`WA_TEMPLATE_NAME`).
- Só números em `WA_ALLOWED_NUMBERS` comandam o bot (lista vazia = ninguém).
- A API do MT5 não é thread-safe: todas as chamadas passam por um RLock em mt5_client.py.

## Arquitetura
```
main.py          FastAPI (painel + API + webhook WhatsApp) e APScheduler
                 jobs: análise a cada ANALYSIS_INTERVAL_MIN, monitor 30 s, expira sinais, resumo diário
engine.py        ciclo de análise -> filtros (limiar por par, notícia, tendência, risco) -> abre trade ou sinal
trades.py        abrir / monitorar / encerrar / estatísticas; finalize -> diagnóstico -> learning.review
diagnostics.py   categorias objetivas da perda/ganho + análise opcional da IA
learning.py      params() vigentes, review() após cada trade, apply()/revert() de correções
risk.py          pausa, limite de operações, perda diária (pausa sozinho), spread
mt5_client.py    conexão, ATR, tendência H4, lote por risco, ordens, fechamento, histórico
whatsapp.py      envio (texto/template), assinatura do webhook, parse de mensagens
commands.py      comandos de texto do WhatsApp
db.py            SQLite: signals, trades (diário), corrections, log, kv
fundamentals/    calendar.py, news.py, macro.py, scorer.py (nota por moeda e por par)
web/index.html   painel: Painel, Diário, Resultados, Correções, Log (JS puro, sem build)
tests/fakes.py          MT5, feedparser e calendário falsos (compartilhados pelos testes)
tests/test_simulado.py  fluxo completo com MT5 falso — roda em Linux/macOS também
tests/test_api.py       rotas da API e webhook do WhatsApp com fastapi.testclient
```

## Como testar
```
pip install -r requirements.txt     # no Windows; para o teste basta requests + python-dotenv
python tests/test_simulado.py       # deve terminar com "OK — todos os testes passaram"
pip install fastapi httpx           # só para o teste da API
python tests/test_api.py            # deve terminar com "OK — todos os testes da API passaram"
```
O teste cobre: surpresas do calendário, abertura automática, bloqueio por notícia, SL/TP,
diagnóstico, risco reduzido após perdas e restaurado após vitória, limiar por par, ajuste de
pesos, desfazer correção, estatísticas e comandos do WhatsApp.
O teste da API cobre: painel servido de qualquer pasta, token (ausente/errado/vazio), todas as
rotas do painel (status, análise, trades, filtros, encerrar, pausar, sinais em modo confirmação,
correções, log), verificação do webhook e mensagens assinadas/não assinadas/não autorizadas.

## O que NÃO foi testado (ambiente sem acesso)
- Conexão real com o MetaTrader 5 (envio de ordem, `history_deals_get`, `filling_mode`).
- Abrir o painel no navegador (as rotas da API têm teste, mas o JS do painel não).
- Webhook real da Meta e chamadas reais à API da Anthropic.

## Próximos passos sugeridos
1. Rodar na VPS em conta **demo** com `DRY_RUN=true`, conferir painel e mensagens.
2. Validar `send_market`/`closed_info` contra a corretora (sufixo de símbolo, modos de preenchimento).
3. Atualizar `macro.json` com taxas e postura reais dos bancos centrais.
4. Configurar app da Meta + Cloudflare Tunnel e testar os comandos (`ajuda`).
5. Deixar acumular ≥ 20 operações simuladas antes de avaliar o aprendizado.
6. Ideias em aberto: backtest com histórico de calendário, edição de `macro.json` pelo painel,
   trocar o modo auto/confirm pelo painel.

## Convenções
- Textos para o usuário em português; código e nomes de variáveis podem ficar em inglês.
- Toda nova regra de aprendizado deve: ter amostra mínima, limite, justificativa gravada,
  ser reversível e nunca aumentar o risco.
- Rodar `python tests/test_simulado.py` após qualquer mudança no fluxo e `python tests/test_api.py`
  após mudanças em main.py, nas rotas ou no webhook.
