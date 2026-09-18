# Vendas_Financeiro

App de controle de vendas, financeiro e estoque para uma loja no iFood, construído
inteiramente em **Google Apps Script** (GAS) — sem servidor próprio, sem custo de
hospedagem. Os dados ficam salvos numa planilha do **Google Sheets** no seu Google
Drive, e o acesso é protegido pelo próprio login da sua Conta do Google.

## O que o app faz

- **Financeiro**: saldo bancário inicial, entradas (vendas), saídas de caixa
  (compras de insumos e despesas manuais) e saldo final calculado automaticamente.
  O custo da produção entra no resultado sem reduzir o caixa uma segunda vez.
  Resumo por período com receita, custo, margem bruta, despesas e lucro líquido.
- **Estoque**: cadastro de insumos (itens comprados) organizados por
  categoria/subcategoria e por estabelecimento (fornecedor). Cada compra soma ao
  estoque e recalcula o custo médio ponderado do insumo.
- **Ficha técnica (receita/BOM)**: para cada produto final (ex: Lasanha, Panqueca)
  você cadastra os ingredientes e a quantidade necessária por unidade.
- **Simulação de produção**: informe quanto quer produzir de cada produto, na
  ordem de prioridade. O app reserva o estoque necessário para o primeiro produto
  antes de calcular o segundo — por isso, se Lasanha e Panqueca usam o mesmo
  ingrediente, ao pedir 5 Lasanhas primeiro o app já mostra corretamente quantas
  Panquecas ainda cabem no estoque restante. O resultado inclui quantidade viável,
  o que faltou (se não coube tudo), custo estimado, receita estimada e margem.
- **Produção real**: ao confirmar uma produção, o app dá baixa de verdade no
  estoque de cada ingrediente e lança o custo como saída financeira.
- **Vendas**: registro das vendas (ex: pelo iFood), gerando automaticamente uma
  entrada financeira.

## Estrutura do repositório

```
apps-script/
  appsscript.json   # manifesto do projeto (permissões, config do web app)
  Setup.gs          # cria a planilha do banco de dados (rodar 1x)
  Utils.gs          # helpers de leitura/escrita na planilha + autorização de usuário
  Cadastros.gs      # categorias, subcategorias, estabelecimentos, insumos, produtos
  Compras.gs        # registro de compras (atualiza estoque e custo médio)
  Receitas.gs       # ficha técnica / BOM de cada produto final
  Producao.gs       # simulação de produção e baixa real de estoque
  Vendas.gs         # registro de vendas
  Financeiro.gs      # saldo, lançamentos, resumo/DRE simplificado
  WebApp.gs         # doGet() e ponte de dados para a interface
  Index.html        # página única (SPA) com todas as telas
  Stylesheet.html   # estilos
  JavaScript.html   # lógica do front-end
```

## Como publicar (passo a passo)

Você vai usar o **clasp**, ferramenta de linha de comando do Google para
sincronizar código local com um projeto Apps Script.

### 1. Pré-requisitos

```bash
npm install -g @google/clasp
clasp login
```

Isso abre o navegador para você autorizar com sua Conta do Google
(`yuritaicer@gmail.com` ou a conta que for usar).

Ative a API do Apps Script (uma vez, por conta): acesse
https://script.google.com/home/usersettings e ligue "Google Apps Script API".

### 2. Criar o projeto Apps Script

Na raiz deste repositório:

```bash
cd apps-script
clasp create --title "Vendas Financeiro - iFood" --type webapp --rootDir .
```

Isso gera um `.clasp.json` local (não commitado — veja `.clasp.json.example`) com
o `scriptId` do novo projeto.

### 3. Enviar o código

```bash
clasp push
```

### 4. Rodar o setup inicial

```bash
clasp open
```

No editor do Apps Script que abrir: selecione a função `setupPlanilha` no topo e
clique em **Executar**. Na primeira execução, o Google vai pedir para você
autorizar as permissões (Planilhas, Drive). Isso cria a planilha
"Vendas_Financeiro - Banco de Dados" no seu Drive, já com todas as abas, e
cadastra seu e-mail como administrador (aba `Usuarios`).

### 5. Implantar como aplicativo web

No editor: **Implantar > Nova implantação**.
- Tipo: **App da Web**
- Executar como: **Usuário que acessa o app da web** (já configurado no manifesto)
- Quem pode acessar: **Qualquer pessoa com Conta do Google**

Copie a URL gerada — é o link do seu app. Ao abrir, o Google pede login com a
Conta do Google (isso já funciona como autenticação); em seguida o app confere
se o e-mail está na aba `Usuarios` da planilha.

### 6. Liberar acesso para outras pessoas (opcional)

Como o app é executado com a identidade de quem o acessa, faça as duas etapas:

1. Compartilhe a planilha "Vendas_Financeiro - Banco de Dados" com o e-mail da
   pessoa, concedendo permissão de **Editor**.
2. Adicione uma linha na aba `Usuarios` com o e-mail, nome e papel (`admin` ou
   `usuario`) da pessoa.

Depois disso, ela poderá acessar o app com a própria Conta do Google, sem nova
implantação. Apenas incluir o e-mail na aba `Usuarios` não concede acesso à
planilha e, sozinho, não é suficiente.

### Atualizações futuras

Sempre que alterar o código, rode `clasp push` (dentro de `apps-script/`) e, se
quiser que a URL publicada reflita a mudança, faça **Implantar > Gerenciar
implantações > editar (lápis) > Nova versão**.

## Próximos passos sugeridos

- Adicionar gráficos de evolução de saldo/vendas no dashboard.
- Alertas automáticos (e-mail) quando um insumo ficar abaixo do estoque mínimo.
- Importação de vendas direto do extrato do iFood (CSV) para reduzir digitação.
