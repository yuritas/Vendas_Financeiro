/**
 * Financeiro.gs
 * Saldo bancário, entradas, saídas e saldo final. Toda compra e toda produção já
 * geram lançamentos automáticos de saída (ver Compras.gs / Producao.gs); toda venda
 * gera lançamento automático de entrada (ver Vendas.gs). Lançamentos manuais (ex:
 * taxa do iFood, aluguel, embalagens) podem ser adicionados aqui.
 */

function getSaldoInicial_() {
  var config = readRows_(SHEET_NAMES.CONFIG);
  var linha = config.filter(function (c) { return c.chave === 'saldoInicial'; })[0];
  return linha ? Number(linha.valor) || 0 : 0;
}

function definirSaldoInicial(valor) {
  exigirAdmin_();
  var sheet = getSheet_(SHEET_NAMES.CONFIG);
  var config = readRows_(SHEET_NAMES.CONFIG);
  var linha = config.filter(function (c) { return c.chave === 'saldoInicial'; })[0];
  if (linha) {
    updateRow_(SHEET_NAMES.CONFIG, linha._row, { valor: Number(valor) });
  } else {
    appendRow_(SHEET_NAMES.CONFIG, { chave: 'saldoInicial', valor: Number(valor) });
  }
  return Number(valor);
}

/** Uso interno: cria lançamento financeiro e recalcula o saldo resultante. */
function registrarLancamentoFinanceiro_(dados) {
  var saldoAtual = getSaldoAtual_();
  var valor = Number(dados.valor);
  var saldoResultante = dados.tipo === 'entrada' ? saldoAtual + valor : saldoAtual - valor;
  var id = nextId_(SHEET_NAMES.FINANCEIRO);
  appendRow_(SHEET_NAMES.FINANCEIRO, {
    id: id,
    data: dados.data || todayStr_(),
    tipo: dados.tipo,
    categoria: dados.categoria || '',
    descricao: dados.descricao || '',
    valor: arred_(valor),
    saldoResultante: arred_(saldoResultante),
    usuario: dados.usuario || ''
  });
  return saldoResultante;
}

/** Lançamento manual (entrada ou saída) feito pelo usuário pela interface. */
function registrarLancamentoManual(dados) {
  var usuario = getUsuarioAtual_();
  if (!dados || !dados.tipo || !dados.valor) throw new Error('Informe tipo (entrada/saida) e valor.');
  if (dados.tipo !== 'entrada' && dados.tipo !== 'saida') throw new Error('Tipo deve ser "entrada" ou "saida".');
  return registrarLancamentoFinanceiro_({
    data: dados.data || todayStr_(),
    tipo: dados.tipo,
    categoria: dados.categoria || 'Outros',
    descricao: dados.descricao || '',
    valor: Number(dados.valor),
    usuario: usuario.email
  });
}

function getSaldoAtual_() {
  var lancamentos = readRows_(SHEET_NAMES.FINANCEIRO);
  if (!lancamentos.length) return getSaldoInicial_();
  var ultimo = lancamentos[lancamentos.length - 1];
  return Number(ultimo.saldoResultante) || 0;
}

function listarLancamentos(limite) {
  getUsuarioAtual_();
  var rows = readRows_(SHEET_NAMES.FINANCEIRO);
  if (limite) rows = rows.slice(Math.max(0, rows.length - limite));
  return rows;
}

/**
 * Resumo financeiro/DRE simplificado num período (datas no formato yyyy-MM-dd).
 * Receita = vendas do período. Custo = produção do período. Despesas = demais saídas.
 */
function resumoFinanceiro(dataInicio, dataFim) {
  getUsuarioAtual_();
  var lancamentos = readRows_(SHEET_NAMES.FINANCEIRO).filter(function (l) {
    return dentroDoPeriodo_(l.data, dataInicio, dataFim);
  });

  var entradas = 0, saidas = 0, custoProducao = 0, despesasGerais = 0;
  lancamentos.forEach(function (l) {
    var valor = Number(l.valor) || 0;
    if (l.tipo === 'entrada') {
      entradas += valor;
    } else {
      saidas += valor;
      if (l.categoria === 'Custo de produção') {
        custoProducao += valor;
      } else {
        despesasGerais += valor;
      }
    }
  });

  var vendas = readRows_(SHEET_NAMES.VENDAS).filter(function (v) {
    return dentroDoPeriodo_(v.data, dataInicio, dataFim);
  });
  var receitaVendas = vendas.reduce(function (soma, v) { return soma + (Number(v.valorTotal) || 0); }, 0);

  return {
    saldoBancarioInicial: arred_(getSaldoInicial_()),
    saldoBancarioAtual: arred_(getSaldoAtual_()),
    periodo: { inicio: dataInicio || null, fim: dataFim || null },
    entradasTotais: arred_(entradas),
    saidasTotais: arred_(saidas),
    receitaVendas: arred_(receitaVendas),
    custoProducao: arred_(custoProducao),
    despesasGerais: arred_(despesasGerais),
    margemBruta: arred_(receitaVendas - custoProducao),
    lucroLiquido: arred_(receitaVendas - custoProducao - despesasGerais)
  };
}

function dentroDoPeriodo_(dataStr, inicio, fim) {
  if (!inicio && !fim) return true;
  var data = String(dataStr);
  if (inicio && data < inicio) return false;
  if (fim && data > fim) return false;
  return true;
}
