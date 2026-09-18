/**
 * Receitas.gs
 * Ficha técnica (BOM - bill of materials) de cada produto final: quais insumos e em
 * que quantidade são consumidos para produzir 1 unidade do produto.
 */

function listarReceita(produtoFinalId) {
  getUsuarioAtual_();
  var rows = readRows_(SHEET_NAMES.RECEITAS);
  if (produtoFinalId) {
    rows = rows.filter(function (r) { return Number(r.produtoFinalId) === Number(produtoFinalId); });
  }
  return rows;
}

/**
 * Substitui a ficha técnica de um produto final pela lista de itens informada.
 * itens: [{ insumoId, quantidadePorUnidade }, ...]
 */
function salvarReceita(produtoFinalId, itens) {
  getUsuarioAtual_();
  if (!produtoFinalId || !itens || !itens.length) {
    throw new Error('Informe o produto final e ao menos um ingrediente.');
  }
  var sheet = getSheet_(SHEET_NAMES.RECEITAS);
  var todas = readRows_(SHEET_NAMES.RECEITAS);

  // Remove linhas antigas desse produto (de baixo para cima para não bagunçar índices).
  todas
    .filter(function (r) { return Number(r.produtoFinalId) === Number(produtoFinalId); })
    .sort(function (a, b) { return b._row - a._row; })
    .forEach(function (r) { sheet.deleteRow(r._row); });

  var proximoId = nextId_(SHEET_NAMES.RECEITAS);
  itens.forEach(function (item) {
    if (!item.insumoId || !item.quantidadePorUnidade) return;
    appendRow_(SHEET_NAMES.RECEITAS, {
      id: proximoId++,
      produtoFinalId: produtoFinalId,
      insumoId: item.insumoId,
      quantidadePorUnidade: Number(item.quantidadePorUnidade)
    });
  });

  return listarReceita(produtoFinalId);
}

/** Retorna a receita agrupada por produtoFinalId -> [{insumoId, quantidadePorUnidade}]. */
function mapaReceitas_() {
  var receitas = readRows_(SHEET_NAMES.RECEITAS);
  var mapa = {};
  receitas.forEach(function (r) {
    var pid = Number(r.produtoFinalId);
    if (!mapa[pid]) mapa[pid] = [];
    mapa[pid].push({ insumoId: Number(r.insumoId), quantidadePorUnidade: Number(r.quantidadePorUnidade) });
  });
  return mapa;
}
