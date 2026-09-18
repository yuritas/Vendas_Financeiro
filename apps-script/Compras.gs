/**
 * Compras.gs
 * Registro de compras de insumos. Cada compra soma quantidade ao estoque do insumo
 * e recalcula o custo unitário médio ponderado (usado depois para custear receitas).
 */

function listarCompras() {
  getUsuarioAtual_();
  return readRows_(SHEET_NAMES.COMPRAS);
}

/**
 * dados: { data, estabelecimentoId, insumoId, quantidade, valorUnitario }
 */
function registrarCompra(dados) {
  var usuario = getUsuarioAtual_();
  if (!dados || !dados.insumoId || !dados.quantidade || dados.valorUnitario === undefined) {
    throw new Error('Informe insumo, quantidade e valor unitário da compra.');
  }
  var quantidade = Number(dados.quantidade);
  var valorUnitario = Number(dados.valorUnitario);
  if (quantidade <= 0) throw new Error('Quantidade deve ser maior que zero.');

  var insumos = readRows_(SHEET_NAMES.INSUMOS);
  var insumo = insumos.filter(function (i) { return Number(i.id) === Number(dados.insumoId); })[0];
  if (!insumo) throw new Error('Insumo não encontrado.');

  var valorTotal = quantidade * valorUnitario;
  var id = nextId_(SHEET_NAMES.COMPRAS);

  appendRow_(SHEET_NAMES.COMPRAS, {
    id: id,
    data: dados.data || todayStr_(),
    estabelecimentoId: dados.estabelecimentoId || '',
    insumoId: dados.insumoId,
    quantidade: quantidade,
    valorUnitario: valorUnitario,
    valorTotal: valorTotal,
    usuario: usuario.email
  });

  // Recalcula estoque e custo médio ponderado do insumo.
  var estoqueAnterior = Number(insumo.estoqueAtual) || 0;
  var custoAnterior = Number(insumo.custoUnitarioMedio) || 0;
  var novoEstoque = estoqueAnterior + quantidade;
  var custoTotalAnterior = estoqueAnterior * custoAnterior;
  var novoCustoMedio = novoEstoque > 0 ? (custoTotalAnterior + valorTotal) / novoEstoque : valorUnitario;

  updateRow_(SHEET_NAMES.INSUMOS, insumo._row, {
    estoqueAtual: novoEstoque,
    custoUnitarioMedio: novoCustoMedio
  });

  // Lançamento financeiro automático de saída (compra de insumo).
  registrarLancamentoFinanceiro_({
    data: dados.data || todayStr_(),
    tipo: 'saida',
    categoria: 'Compra de insumo',
    descricao: 'Compra: ' + insumo.nome + ' (' + quantidade + ' ' + insumo.unidade + ')',
    valor: valorTotal,
    impactaSaldo: true,
    usuario: usuario.email
  });

  return { id: id, valorTotal: valorTotal, novoEstoque: novoEstoque, novoCustoMedio: novoCustoMedio };
}
