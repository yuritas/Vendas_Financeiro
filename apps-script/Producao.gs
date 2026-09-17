/**
 * Producao.gs
 * Núcleo do controle de estoque para produção: dado o estoque atual de insumos e a
 * ficha técnica de cada produto final, estima quantas unidades de cada produto dá
 * para produzir - respeitando reservas já feitas para outros produtos que competem
 * pelos mesmos ingredientes (ex: massa/queijo usados tanto em lasanha quanto em
 * outra receita).
 */

/** Estoque disponível hoje, por insumoId. */
function estoqueDisponivel_() {
  var insumos = readRows_(SHEET_NAMES.INSUMOS);
  var mapa = {};
  insumos.forEach(function (i) { mapa[Number(i.id)] = Number(i.estoqueAtual) || 0; });
  return mapa;
}

/**
 * Quantas unidades de um produto final dá para produzir com o estoque disponível informado
 * (sem alterar nada), considerando sua ficha técnica.
 */
function maxProducaoPossivel_(produtoFinalId, estoque, receitas) {
  var itens = receitas[Number(produtoFinalId)] || [];
  if (!itens.length) return 0;
  var max = Infinity;
  itens.forEach(function (item) {
    var disponivel = estoque[item.insumoId] || 0;
    var possivel = Math.floor(disponivel / item.quantidadePorUnidade);
    if (possivel < max) max = possivel;
  });
  return max === Infinity ? 0 : max;
}

/**
 * Simula uma sequência de pedidos de produção, reservando estoque na ordem informada,
 * e devolve, para cada pedido, se cabe no estoque, o custo estimado e - ao final -
 * quanto ainda dá para produzir de CADA produto final ativo com o estoque restante.
 *
 * pedidos: [{ produtoFinalId, quantidade }]  (ordem = prioridade de reserva)
 */
function simularProducao(pedidos) {
  getUsuarioAtual_();
  if (!pedidos || !pedidos.length) throw new Error('Informe ao menos um produto para simular.');

  var estoque = estoqueDisponivel_();
  var receitas = mapaReceitas_();
  var insumos = readRows_(SHEET_NAMES.INSUMOS);
  var insumosPorId = {};
  insumos.forEach(function (i) { insumosPorId[Number(i.id)] = i; });
  var produtos = readRows_(SHEET_NAMES.PRODUTOS_FINAIS);
  var produtosPorId = {};
  produtos.forEach(function (p) { produtosPorId[Number(p.id)] = p; });

  var resultadoPedidos = [];
  var receitaTotal = 0;
  var custoTotal = 0;

  pedidos.forEach(function (pedido) {
    var pid = Number(pedido.produtoFinalId);
    var quantidadeDesejada = Number(pedido.quantidade);
    var produto = produtosPorId[pid];
    if (!produto) throw new Error('Produto final não encontrado: ' + pid);

    var itens = receitas[pid] || [];
    if (!itens.length) throw new Error('Produto "' + produto.nome + '" não tem ficha técnica cadastrada.');

    var maxPossivelAgora = maxProducaoPossivel_(pid, estoque, receitas);
    var quantidadeViavel = Math.min(quantidadeDesejada, maxPossivelAgora);
    var atendeTotalmente = quantidadeViavel >= quantidadeDesejada;

    var faltas = [];
    var custoPedido = 0;
    itens.forEach(function (item) {
      var necessario = item.quantidadePorUnidade * quantidadeViavel;
      var insumo = insumosPorId[item.insumoId];
      custoPedido += necessario * (Number(insumo.custoUnitarioMedio) || 0);
      // Reserva (deduz) do estoque disponível para os próximos pedidos da simulação.
      estoque[item.insumoId] -= necessario;

      if (!atendeTotalmente) {
        var faltou = (item.quantidadePorUnidade * quantidadeDesejada) - (item.quantidadePorUnidade * quantidadeViavel);
        if (faltou > 0.0001) {
          faltas.push({ insumoId: item.insumoId, insumoNome: insumo.nome, faltando: faltou, unidade: insumo.unidade });
        }
      }
    });

    var receitaPedido = quantidadeViavel * (Number(produto.precoVenda) || 0);
    receitaTotal += receitaPedido;
    custoTotal += custoPedido;

    resultadoPedidos.push({
      produtoFinalId: pid,
      produtoNome: produto.nome,
      quantidadeDesejada: quantidadeDesejada,
      quantidadeViavel: quantidadeViavel,
      atendeTotalmente: atendeTotalmente,
      faltas: faltas,
      custoEstimado: arred_(custoPedido),
      receitaEstimada: arred_(receitaPedido),
      margemEstimada: arred_(receitaPedido - custoPedido)
    });
  });

  // Com o que sobrou de estoque (após reservar todos os pedidos acima), estima quanto
  // ainda dá para produzir de cada produto ativo - inclusive dos que não estavam no pedido.
  var estimativaRestante = produtos
    .filter(function (p) { return String(p.ativo).toUpperCase() !== 'FALSE'; })
    .map(function (p) {
      var max = maxProducaoPossivel_(p.id, estoque, receitas);
      return { produtoFinalId: Number(p.id), produtoNome: p.nome, maxProducaoComEstoqueRestante: max };
    });

  return {
    pedidos: resultadoPedidos,
    resumo: {
      receitaEstimada: arred_(receitaTotal),
      custoEstimado: arred_(custoTotal),
      margemEstimada: arred_(receitaTotal - custoTotal)
    },
    estoqueRestanteEstimativaProducao: estimativaRestante
  };
}

/**
 * Registra produção de fato: dá baixa real no estoque de insumos, grava na aba Producao
 * e cria lançamento financeiro de custo (saída). Use depois de simularProducao() confirmar
 * que cabe no estoque.
 */
function registrarProducao(produtoFinalId, quantidade) {
  var usuario = getUsuarioAtual_();
  var pid = Number(produtoFinalId);
  quantidade = Number(quantidade);
  if (!pid || quantidade <= 0) throw new Error('Informe produto e quantidade válidos.');

  var receitas = mapaReceitas_();
  var itens = receitas[pid] || [];
  if (!itens.length) throw new Error('Produto não tem ficha técnica cadastrada.');

  var insumos = readRows_(SHEET_NAMES.INSUMOS);
  var insumosPorId = {};
  insumos.forEach(function (i) { insumosPorId[Number(i.id)] = i; });

  // Confere se há estoque suficiente antes de baixar qualquer coisa.
  itens.forEach(function (item) {
    var insumo = insumosPorId[item.insumoId];
    var necessario = item.quantidadePorUnidade * quantidade;
    if ((Number(insumo.estoqueAtual) || 0) < necessario) {
      throw new Error('Estoque insuficiente de "' + insumo.nome + '" para produzir ' + quantidade + ' unidade(s).');
    }
  });

  var custoTotal = 0;
  itens.forEach(function (item) {
    var insumo = insumosPorId[item.insumoId];
    var necessario = item.quantidadePorUnidade * quantidade;
    custoTotal += necessario * (Number(insumo.custoUnitarioMedio) || 0);
    updateRow_(SHEET_NAMES.INSUMOS, insumo._row, { estoqueAtual: Number(insumo.estoqueAtual) - necessario });
  });

  var produtos = readRows_(SHEET_NAMES.PRODUTOS_FINAIS);
  var produto = produtos.filter(function (p) { return Number(p.id) === pid; })[0];

  var id = nextId_(SHEET_NAMES.PRODUCAO);
  appendRow_(SHEET_NAMES.PRODUCAO, {
    id: id,
    data: todayStr_(),
    produtoFinalId: pid,
    quantidadeProduzida: quantidade,
    custoTotal: arred_(custoTotal),
    usuario: usuario.email
  });

  registrarLancamentoFinanceiro_({
    data: todayStr_(),
    tipo: 'saida',
    categoria: 'Custo de produção',
    descricao: 'Produção: ' + quantidade + ' x ' + (produto ? produto.nome : pid),
    valor: arred_(custoTotal),
    usuario: usuario.email
  });

  return { id: id, custoTotal: arred_(custoTotal) };
}

function arred_(n) {
  return Math.round((Number(n) || 0) * 100) / 100;
}
