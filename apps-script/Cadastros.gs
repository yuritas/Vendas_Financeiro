/**
 * Cadastros.gs
 * CRUD de Estabelecimentos, Categorias, Subcategorias e Insumos (itens de estoque).
 */

function listarEstabelecimentos() {
  getUsuarioAtual_();
  return readRows_(SHEET_NAMES.ESTABELECIMENTOS);
}

function salvarEstabelecimento(nome, observacao) {
  getUsuarioAtual_();
  if (!nome) throw new Error('Informe o nome do estabelecimento.');
  var id = nextId_(SHEET_NAMES.ESTABELECIMENTOS);
  return appendRow_(SHEET_NAMES.ESTABELECIMENTOS, { id: id, nome: nome, observacao: observacao || '' });
}

function listarCategorias() {
  getUsuarioAtual_();
  return readRows_(SHEET_NAMES.CATEGORIAS);
}

function salvarCategoria(nome) {
  getUsuarioAtual_();
  if (!nome) throw new Error('Informe o nome da categoria.');
  var id = nextId_(SHEET_NAMES.CATEGORIAS);
  return appendRow_(SHEET_NAMES.CATEGORIAS, { id: id, nome: nome });
}

function listarSubcategorias(categoriaId) {
  getUsuarioAtual_();
  var rows = readRows_(SHEET_NAMES.SUBCATEGORIAS);
  if (categoriaId) {
    rows = rows.filter(function (r) { return Number(r.categoriaId) === Number(categoriaId); });
  }
  return rows;
}

function salvarSubcategoria(categoriaId, nome) {
  getUsuarioAtual_();
  if (!categoriaId || !nome) throw new Error('Informe categoria e nome da subcategoria.');
  var id = nextId_(SHEET_NAMES.SUBCATEGORIAS);
  return appendRow_(SHEET_NAMES.SUBCATEGORIAS, { id: id, categoriaId: categoriaId, nome: nome });
}

function listarInsumos() {
  getUsuarioAtual_();
  return readRows_(SHEET_NAMES.INSUMOS);
}

/**
 * Cria um novo insumo (item de estoque). O estoque começa zerado; para entrar com
 * quantidade inicial, registre uma Compra logo em seguida.
 */
function salvarInsumo(dados) {
  getUsuarioAtual_();
  if (!dados || !dados.nome || !dados.unidade) {
    throw new Error('Informe nome e unidade do insumo.');
  }
  var id = nextId_(SHEET_NAMES.INSUMOS);
  return appendRow_(SHEET_NAMES.INSUMOS, {
    id: id,
    nome: dados.nome,
    categoriaId: dados.categoriaId || '',
    subcategoriaId: dados.subcategoriaId || '',
    unidade: dados.unidade,
    estoqueAtual: 0,
    estoqueMinimo: dados.estoqueMinimo || 0,
    custoUnitarioMedio: 0
  });
}

function listarProdutosFinais() {
  getUsuarioAtual_();
  return readRows_(SHEET_NAMES.PRODUTOS_FINAIS);
}

function salvarProdutoFinal(dados) {
  getUsuarioAtual_();
  if (!dados || !dados.nome || !dados.precoVenda) {
    throw new Error('Informe nome e preço de venda do produto final.');
  }
  var id = nextId_(SHEET_NAMES.PRODUTOS_FINAIS);
  return appendRow_(SHEET_NAMES.PRODUTOS_FINAIS, {
    id: id,
    nome: dados.nome,
    categoria: dados.categoria || '',
    precoVenda: Number(dados.precoVenda),
    quantidadePadraoLote: Number(dados.quantidadePadraoLote) || 1,
    ativo: true
  });
}
