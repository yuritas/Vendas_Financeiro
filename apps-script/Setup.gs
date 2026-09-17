/**
 * Setup.gs
 * Rode a função setupPlanilha() UMA VEZ (menu Executar > setupPlanilha) para criar
 * a planilha do banco de dados com todas as abas e cabeçalhos necessários.
 * Quem rodar pela primeira vez é cadastrado automaticamente como administrador.
 */
function setupPlanilha() {
  var ss = getDb();

  var abas = {};
  abas[SHEET_NAMES.CONFIG] = ['chave', 'valor'];
  abas[SHEET_NAMES.USUARIOS] = ['id', 'email', 'nome', 'papel', 'ativo'];
  abas[SHEET_NAMES.ESTABELECIMENTOS] = ['id', 'nome', 'observacao'];
  abas[SHEET_NAMES.CATEGORIAS] = ['id', 'nome'];
  abas[SHEET_NAMES.SUBCATEGORIAS] = ['id', 'categoriaId', 'nome'];
  abas[SHEET_NAMES.INSUMOS] = ['id', 'nome', 'categoriaId', 'subcategoriaId', 'unidade', 'estoqueAtual', 'estoqueMinimo', 'custoUnitarioMedio'];
  abas[SHEET_NAMES.COMPRAS] = ['id', 'data', 'estabelecimentoId', 'insumoId', 'quantidade', 'valorUnitario', 'valorTotal', 'usuario'];
  abas[SHEET_NAMES.PRODUTOS_FINAIS] = ['id', 'nome', 'categoria', 'precoVenda', 'quantidadePadraoLote', 'ativo'];
  abas[SHEET_NAMES.RECEITAS] = ['id', 'produtoFinalId', 'insumoId', 'quantidadePorUnidade'];
  abas[SHEET_NAMES.PRODUCAO] = ['id', 'data', 'produtoFinalId', 'quantidadeProduzida', 'custoTotal', 'usuario'];
  abas[SHEET_NAMES.VENDAS] = ['id', 'data', 'produtoFinalId', 'quantidade', 'valorUnitario', 'valorTotal', 'canal', 'usuario'];
  abas[SHEET_NAMES.FINANCEIRO] = ['id', 'data', 'tipo', 'categoria', 'descricao', 'valor', 'saldoResultante', 'usuario'];

  Object.keys(abas).forEach(function (nome) {
    var sheet = ss.getSheetByName(nome);
    if (!sheet) {
      sheet = ss.insertSheet(nome);
    }
    var headers = abas[nome];
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    sheet.setFrozenRows(1);
    sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  });

  // Remove a aba padrão "Sheet1"/"Página1" se ainda existir vazia.
  var padrao = ss.getSheetByName('Sheet1') || ss.getSheetByName('Página1');
  if (padrao && ss.getSheets().length > 1) {
    ss.deleteSheet(padrao);
  }

  // Cadastra quem rodou o setup como administrador, se a lista de usuários estiver vazia.
  var usuarios = readRows_(SHEET_NAMES.USUARIOS);
  if (usuarios.length === 0) {
    var meuEmail = Session.getActiveUser().getEmail() || Session.getEffectiveUser().getEmail();
    appendRow_(SHEET_NAMES.USUARIOS, {
      id: 1,
      email: meuEmail,
      nome: meuEmail.split('@')[0],
      papel: 'admin',
      ativo: true
    });
  }

  // Config inicial: saldo bancário de partida.
  var config = readRows_(SHEET_NAMES.CONFIG);
  var temSaldoInicial = config.some(function (c) { return c.chave === 'saldoInicial'; });
  if (!temSaldoInicial) {
    appendRow_(SHEET_NAMES.CONFIG, { chave: 'saldoInicial', valor: 0 });
  }

  Logger.log('Planilha configurada: ' + ss.getUrl());
  return ss.getUrl();
}
