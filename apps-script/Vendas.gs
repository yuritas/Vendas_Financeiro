/**
 * Vendas.gs
 * Registro de vendas realizadas (ex: pelo iFood). Cada venda gera automaticamente
 * um lançamento financeiro de entrada.
 */

function listarVendas() {
  getUsuarioAtual_();
  return readRows_(SHEET_NAMES.VENDAS);
}

/**
 * dados: { data, produtoFinalId, quantidade, valorUnitario (opcional, usa preço cadastrado se omitido), canal }
 */
function registrarVenda(dados) {
  var usuario = getUsuarioAtual_();
  if (!dados || !dados.produtoFinalId || !dados.quantidade) {
    throw new Error('Informe produto e quantidade vendida.');
  }
  var produtos = readRows_(SHEET_NAMES.PRODUTOS_FINAIS);
  var produto = produtos.filter(function (p) { return Number(p.id) === Number(dados.produtoFinalId); })[0];
  if (!produto) throw new Error('Produto final não encontrado.');

  var quantidade = Number(dados.quantidade);
  var valorUnitario = dados.valorUnitario !== undefined && dados.valorUnitario !== ''
    ? Number(dados.valorUnitario)
    : Number(produto.precoVenda);
  var valorTotal = arred_(quantidade * valorUnitario);

  var id = nextId_(SHEET_NAMES.VENDAS);
  appendRow_(SHEET_NAMES.VENDAS, {
    id: id,
    data: dados.data || todayStr_(),
    produtoFinalId: dados.produtoFinalId,
    quantidade: quantidade,
    valorUnitario: valorUnitario,
    valorTotal: valorTotal,
    canal: dados.canal || 'iFood',
    usuario: usuario.email
  });

  registrarLancamentoFinanceiro_({
    data: dados.data || todayStr_(),
    tipo: 'entrada',
    categoria: 'Venda',
    descricao: 'Venda ' + (dados.canal || 'iFood') + ': ' + quantidade + ' x ' + produto.nome,
    valor: valorTotal,
    impactaSaldo: true,
    usuario: usuario.email
  });

  return { id: id, valorTotal: valorTotal };
}
