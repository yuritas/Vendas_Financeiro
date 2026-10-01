# ForexBot — análise fundamentalista + MetaTrader 5 + WhatsApp + painel web

Sistema em Python que analisa os fundamentos das 8 moedas principais, **abre as operações
sozinho** no MetaTrader 5 e reporta tudo no WhatsApp e no painel web. Cada entrada fica
documentada com a justificativa; cada saída recebe um diagnóstico; e um módulo de
aprendizado ajusta os parâmetros a partir dos erros — com cada correção registrada,
justificada e reversível.

> ⚠️ Forex alavancado pode gerar perdas maiores que o esperado. Rode primeiro em **conta demo**
> e com `DRY_RUN=true` (padrão) até confiar no comportamento. Isto não é recomendação de investimento.

## Como funciona

```
 Calendário econômico ─┐
 Notícias + IA (Claude) ├─► nota por moeda (-5..+5) × pesos aprendidos ─► nota do par
 Juros / postura do BC ─┘                                                   │
            nota ≥ limiar (por par)? notícia forte perto? filtro de tendência? risco ok?
                                                                            │
                 abre a operação (lote por risco, SL/TP por ATR) ─► WhatsApp + Diário
                                                                            │
                         monitor a cada 30 s: stop, alvo ou encerramento manual
                                                                            │
               diagnóstico (regras + IA) ─► aprendizado ─► correções ─► WhatsApp + painel
```

| Pilar | Fonte | O que mede |
|---|---|---|
| Calendário | feed semanal da Forex Factory | surpresa do dado (resultado vs. previsão), ponderada por impacto e com decaimento de 48h |
| Notícias | RSS (FXStreet por padrão) + Claude | viés de cada moeda nas próximas 24h; também extrai das manchetes os resultados dos dados do calendário |
| Juros | `macro.json` (você mantém) | diferencial de juros vs. média + postura hawkish/dovish |

O feed do calendário **não traz o resultado** dos dados — por isso a IA lê o resultado nas
manchetes. Sem `ANTHROPIC_API_KEY`, o pilar de notícias e as surpresas do calendário ficam
zerados e só o pilar de juros funciona.

### Modos de execução
- `EXECUTION_MODE=auto` (padrão): abre sozinho e avisa no WhatsApp com a justificativa.
- `EXECUTION_MODE=confirm`: cria o sinal e espera `SIM <id>`.
- **Modo simulado** (`DRY_RUN=true`, padrão): usa os preços reais do MT5, verifica stop/alvo
  a cada 30 s e alimenta o diário, os diagnósticos e o aprendizado — sem enviar ordem.
  Ideal para o sistema acumular histórico antes de arriscar dinheiro.
- **Trava para conta real:** em conta real, modo `auto` e `DRY_RUN=false`, o sistema continua
  simulando até você definir `ALLOW_REAL_AUTO=true`. É uma confirmação consciente.

### Diário, diagnóstico e aprendizado
Cada operação registra: justificativa da entrada, contribuição de cada pilar, nota e limiar
exigido, tendência H4, spread, risco em dinheiro e os parâmetros vigentes. Ao encerrar:
resultado em dinheiro e em **R** (múltiplos do risco), motivo da saída e diagnóstico.

O diagnóstico classifica a causa (notícia forte durante a operação, stop na primeira hora,
fundamentos que viraram, sinal no limite mínimo, contra a tendência, spread alto). Com
`ANTHROPIC_API_KEY`, a IA escreve uma análise, a lição e uma sugestão — **sugestões da IA
não são aplicadas automaticamente**.

O aprendizado aplica correções só por regras estatísticas, com amostra mínima e limites:

| Situação | Correção | Limite |
|---|---|---|
| `MAX_CONSEC_LOSSES` perdas seguidas | risco pela metade até a próxima vitória | nunca acima do configurado |
| par com expectativa < −0,25R em ≥ 8 trades | exige +0,5 de nota naquele par | até +2,0 |
| pilar correlacionado com o resultado (≥ 20 trades) | peso ±0,1 | 0,3 a 1,7 |
| ≥ 40% das perdas recentes com notícia forte | janela de bloqueio +15 min | até 120 min |
| ≥ 50% das perdas são stops na 1ª hora | stop +0,25×ATR (lote menor, mesmo risco) | até 2,5×ATR |
| ≥ 50% das perdas vieram de sinais no limite | +0,25 no limiar geral | até +1,5 |
| contra a tendência rende 0,4R pior (≥ 10 de cada) | liga filtro de tendência H4 | — |

Cada correção mostra justificativa e evidência na aba **Correções** e no WhatsApp, e pode ser
desfeita (`desfazer <n>` ou botão no painel). Seja realista: com poucas dezenas de operações
os números ainda são muito ruidosos, e nenhum ajuste garante lucro.

### Proteções
- Bloqueio de novas ordens `NEWS_BLACKOUT_MIN` minutos antes/depois de notícia de alto impacto.
- Lote calculado para arriscar `RISK_PER_TRADE`% do saldo até o stop.
- Máximo de posições simultâneas, uma por par, filtro de spread.
- Ao atingir `MAX_DAILY_LOSS`% no dia, o sistema **se pausa sozinho**.
- `fechar tudo` (WhatsApp) ou o botão do painel encerram todas as operações do robô.
- Só números em `WA_ALLOWED_NUMBERS` podem dar comandos (lista vazia = ninguém).

## Estrutura

```
main.py            API web, webhook do WhatsApp e agendador
engine.py          ciclo de análise, entrada automática/sinais, resumo diário
trades.py          abertura, monitoramento, encerramento, estatísticas
diagnostics.py     diagnóstico pós-operação (regras + IA)
learning.py        correções automáticas com justificativa e reversão
risk.py            regras de risco e pausa
mt5_client.py      conexão, cotações, ATR, lote, envio/fechamento de ordens
whatsapp.py        envio e webhook da Meta Cloud API
commands.py        comandos de texto do WhatsApp
fundamentals/      calendar.py, news.py, macro.py, scorer.py
web/index.html     painel
macro.json         juros e postura dos BCs (ATUALIZE)
tests/             testes com MT5 simulado (fluxo completo e API)
```

## Instalação na VPS Windows

1. Instale o **MetaTrader 5** da sua corretora, faça login e marque
   *Ferramentas › Opções › Expert Advisors › Permitir negociação algorítmica*.
2. Instale **Python 3.11+ (64 bits)** marcando "Add to PATH".
3. Na pasta do projeto:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   copy .env.example .env
   ```
4. Edite o `.env` (login MT5, `WEB_TOKEN`, chaves) e o `macro.json` com as taxas atuais.
   Se os símbolos da corretora tiverem sufixo (ex.: `EURUSD.a`), preencha `SYMBOL_SUFFIX`.
5. Teste a lógica (não precisa do MT5): `python tests\test_simulado.py` e `python tests\test_api.py`
   (o teste da API precisa também de `pip install httpx`)
6. Rode: `python main.py` e abra `http://127.0.0.1:8000` na VPS.

Para iniciar com o Windows, crie uma tarefa no *Agendador de Tarefas* executando
`.venv\Scripts\python.exe main.py` na pasta do projeto (ou use o NSSM para virar serviço).

## Acesso externo (HTTPS)

O webhook do WhatsApp exige HTTPS público, e o painel precisa ser acessível do celular.
Mais simples: **Cloudflare Tunnel** (`cloudflared tunnel --url http://localhost:8000`), que
dá um endereço HTTPS sem abrir portas. Mantenha `WEB_HOST=127.0.0.1`.

## WhatsApp (Meta Cloud API)

1. Em developers.facebook.com crie um app do tipo *Business* e adicione o produto **WhatsApp**.
2. Copie o **Phone number ID** → `WA_PHONE_NUMBER_ID`; gere um **token permanente**
   (usuário do sistema no Business Manager) → `WA_TOKEN`; copie o **App Secret** → `WA_APP_SECRET`.
3. Em *Configuração › Webhook*: URL `https://SEU-ENDERECO/webhook`, token de verificação igual
   ao `WA_VERIFY_TOKEN`, e assine o campo **messages**.
4. Coloque seu número em `WA_ALLOWED_NUMBERS` (ex.: `5511999998888`).

**Janela de 24h:** a Meta só entrega mensagens livres se você falou com o bot nas últimas 24h.
Mande "status" uma vez por dia, ou crie um template (categoria *Utilidade*, corpo com `{{1}}`)
e coloque o nome em `WA_TEMPLATE_NAME` — o bot usa o template quando a mensagem livre falhar.

### Comandos
| Comando | Ação |
|---|---|
| `status` | saldo, resultado do dia, operações abertas |
| `abertas` | operações abertas com flutuante em R |
| `fechar 12` / `fechar tudo` | encerra o trade 12 / todos |
| `diario` | últimas operações com resultado e causa |
| `trade 12` | justificativa, diagnóstico e lição do trade 12 |
| `resultado` | acerto, expectativa, fator de lucro, drawdown |
| `correcoes` / `desfazer 3` | correções do aprendizado / desfaz a 3 |
| `analise` / `agenda` / `analisar` | notas por moeda / próximas notícias / análise agora |
| `pausar` / `retomar` | liga/desliga novas entradas |

Avisos automáticos: entrada aberta (com o porquê), saída (resultado e diagnóstico),
correção aplicada, limite de perda diária e um resumo diário às `DAILY_REPORT_HOUR` h.

## Painel web
- **Painel:** saldo, resultado do dia, operações abertas (encerrar com um toque), notas por moeda e agenda.
- **Diário:** todas as operações; toque numa linha para ver justificativa, pilares, diagnóstico e lição.
- **Resultados:** curva de resultado, R por operação, desempenho por par, causas das perdas e quanto cada pilar ajuda.
- **Correções:** parâmetros em uso e histórico de correções com evidência e botão de desfazer.
- **Log:** tudo o que o sistema fez, inclusive oportunidades descartadas e o motivo.

## Ajustes finos
- `SIGNAL_THRESHOLD`: quanto maior, menos sinais e mais seletivos.
- `W_CALENDAR`, `W_NEWS`, `W_MACRO`: peso de cada pilar.
- `SL_ATR_MULT` / `TP_ATR_MULT`: distância do stop e do alvo em múltiplos do ATR(14) de H1.
- `NEWS_FEEDS`: aceita vários RSS separados por vírgula.

## Limitações conhecidas
- No modo simulado o stop/alvo é verificado a cada 30 s; picos rápidos entre verificações podem não ser vistos.
- `macro.json` é manual: atualize após cada reunião de banco central.
- A biblioteca `MetaTrader5` só roda no Windows, com o terminal aberto.
- Não há backtest: valide em demo por algumas semanas antes de usar dinheiro real.
