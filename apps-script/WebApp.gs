/**
 * WebApp.gs
 * Ponto de entrada do aplicativo web. O login é o próprio login Google exigido pela
 * implantação (Configurações de implantação > "Quem pode acessar" = "Qualquer pessoa
 * com Conta do Google"). Depois disso, o e-mail é conferido contra a aba "Usuarios".
 */
function doGet(e) {
  var template = HtmlService.createTemplateFromFile('Index');
  try {
    template.usuario = getUsuarioAtual_();
    template.erro = null;
  } catch (err) {
    template.usuario = null;
    template.erro = err.message;
  }
  return template.evaluate()
    .setTitle('Vendas Financeiro - iFood')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

function include(filename) {
  return HtmlService.createHtmlOutputFromFile(filename).getContent();
}

/** Carrega, numa única chamada, tudo que o dashboard inicial precisa. */
function carregarDadosIniciais() {
  var usuario = getUsuarioAtual_();
  return {
    usuario: usuario,
    estabelecimentos: listarEstabelecimentos(),
    categorias: listarCategorias(),
    subcategorias: listarSubcategorias(),
    insumos: listarInsumos(),
    produtosFinais: listarProdutosFinais(),
    compras: listarCompras().slice(-20).reverse(),
    vendas: listarVendas().slice(-20).reverse(),
    lancamentos: listarLancamentos(20).reverse(),
    resumoFinanceiro: resumoFinanceiro(null, null)
  };
}
