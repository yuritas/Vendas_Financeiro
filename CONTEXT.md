# CONTEXT.md — Vendas_Financeiro

Contexto para continuar este projeto em outra conversa/sessão.

## O que é

App de controle de vendas (loja no iFood), financeiro e estoque, construído
**inteiramente em Google Apps Script** (sem servidor próprio). Os dados ficam
numa planilha do Google Sheets no Google Drive do usuário. A autenticação é o
próprio login da Conta Google (exigido pela implantação do app da web); dentro
do app, o e-mail logado é conferido contra uma aba `Usuarios` na planilha.

- Repositório: `yuritas/Vendas_Financeiro` (GitHub)
- Branch de desenvolvimento: `claude/ifood-sales-control-app-osf7h6`
- Pull Request aberto: **https://github.com/yuritas/Vendas_Financeiro/pull/1**
  (branch → `main`, ainda não mergeado)
- E-mail do usuário/dono: `yuritaicer@gmail.com`

## Decisões já tomadas (não perguntar de novo)

1. **Stack**: Google Apps Script (backend + frontend via HtmlService).
2. **Banco de dados**: Google Sheets, dentro do Google Drive do usuário.
   A planilha é criada automaticamente pela função `setupPlanilha()` (não
   existe ainda — só é criada quando alguém rodar essa função pela primeira
   vez dentro do editor do Apps Script).
3. **Autenticação**: login da própria Conta Google (manifest `access: "ANYONE"`
   = "qualquer pessoa com Conta do Google" — funciona com Gmail pessoal, não
   precisa de domínio Workspace). Dentro do código, `getUsuarioAtual_()`
   confere o e-mail contra a aba `Usuarios`. Quem rodar `setupPlanilha()`
   primeiro vira admin automaticamente.

## Estado atual do código (já implementado e no PR #1)

Pasta `apps-script/`:

| Arquivo | Função |
|---|---|
| `appsscript.json` | Manifesto (permissões, config do web app) |
| `Setup.gs` | `setupPlanilha()` — cria a planilha e todas as abas (rodar 1x) |
| `Utils.gs` | Helpers de leitura/escrita na planilha + `getUsuarioAtual_()` (autorização) |
| `Cadastros.gs` | CRUD de categorias, subcategorias, estabelecimentos, insumos, produtos finais |
| `Compras.gs` | Registro de compras → soma estoque, recalcula custo médio ponderado, lança saída financeira |
| `Receitas.gs` | Ficha técnica (BOM) por produto final: quais insumos e quantidade por unidade |
| `Producao.gs` | **Núcleo do app**: `simularProducao(pedidos)` reserva estoque na ordem informada (ex: 5 lasanhas primeiro, depois panquecas) e calcula quanto ainda dá pra produzir de cada produto com o estoque restante, custo/receita/margem estimados. `registrarProducao()` dá baixa real no estoque. |
| `Vendas.gs` | Registro de vendas (iFood) → lança entrada financeira automática |
| `Financeiro.gs` | Saldo bancário inicial/atual, lançamentos (auto + manuais), `resumoFinanceiro(inicio, fim)` tipo DRE simplificado (receita, custo produção, despesas, margem bruta, lucro líquido) |
| `WebApp.gs` | `doGet()` — ponto de entrada do app web, autoriza usuário, injeta dados |
| `Index.html` | Página única (SPA): abas Dashboard / Estoque / Compras / Fichas Técnicas / Produção / Vendas / Financeiro |
| `Stylesheet.html` | CSS (cores do iFood, cards, tabelas, responsivo mobile) |
| `JavaScript.html` | Lógica do front-end: chama funções do back-end via `google.script.run`, renderiza tabelas/cards, roda o simulador de produção |

Raiz do repo: `README.md` (passo a passo de deploy via clasp), `.clasp.json.example`,
`.claspignore`, `.gitignore`.

Sintaxe de todos os `.gs` já validada com `node --check` (copiando para `.js`
temporário, já que GAS roda um JS ES5-ish). Na retomada de 18/09/2026, foi
corrigida a dupla redução do saldo: compras movimentam o caixa; o custo de
produção compõe o resultado, mas não reduz novamente o saldo bancário. Também
foi documentado que usuários adicionais precisam receber acesso de Editor à
planilha, além do cadastro na aba `Usuarios`. **Ainda não foi testado rodando de
verdade** dentro do Apps Script (nunca foi feito `clasp push` real nem
`setupPlanilha()`).

## O que falta (próximos passos)

Nesta ordem:

1. **Deploy real** (usuário vai fazer isso, possivelmente noutra sessão/chat):
   ```bash
   npm install -g @google/clasp
   clasp login          # abre navegador, autoriza com yuritaicer@gmail.com
   cd apps-script
   clasp create --title "Vendas Financeiro - iFood" --type webapp --rootDir .
   clasp push
   clasp open           # abre o editor do Apps Script no navegador
   ```
   No editor: selecionar `setupPlanilha` no topo → Executar → autorizar
   permissões (Planilhas, Drive) quando o Google pedir.

   Depois: **Implantar → Nova implantação → App da Web**
   - Executar como: "Usuário que acessa o app da web" (já vem assim no manifest)
   - Quem pode acessar: "Qualquer pessoa com Conta do Google"
   - Copiar a URL gerada = link do app.

   Detalhes completos já estão no `README.md` do repo.

2. **Teste end-to-end manual** na interface web:
   cadastro de insumo → compra → ficha técnica → simulação de produção →
   produção real → venda → conferir extrato financeiro batendo.

3. **Merge do PR #1** para `main` depois que o deploy/teste confirmar que está
   funcionando (ninguém revisou/testou ainda).

4. Possíveis melhorias futuras (não pedidas ainda, só sugestões que já demos
   ao usuário): gráficos de evolução de saldo/vendas no dashboard; alerta por
   e-mail quando insumo cair abaixo do estoque mínimo; importação de vendas
   direto de CSV exportado do iFood.

## Limitação importante para quem retomar

Este ambiente (sessão atual do Claude Code) **não tem clasp autenticado nem
acesso interativo a um navegador Google para fazer login/OAuth** — por isso o
deploy real (`clasp login`, autorizar permissões, implantar) precisa ser feito
pelo próprio usuário, no computador dele ou numa sessão que tenha navegador
disponível. O código-fonte está 100% pronto e commitado; falta só publicar.

Se a próxima sessão tiver acesso a um navegador (Claude in Chrome ou navegador
interno), ainda assim o login Google/OAuth do `clasp login` e as telas de
consentimento de permissões da conta pessoal do usuário normalmente exigem
interação humana direta (2FA, tela de consentimento) — o mais seguro é o
usuário fazer esses cliques ele mesmo, com o assistente orientando passo a
passo.
