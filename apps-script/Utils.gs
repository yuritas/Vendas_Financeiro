/**
 * Utilitários compartilhados: acesso à planilha, IDs, autorização de usuários.
 */

var SHEET_NAMES = {
  CONFIG: 'Config',
  USUARIOS: 'Usuarios',
  ESTABELECIMENTOS: 'Estabelecimentos',
  CATEGORIAS: 'Categorias',
  SUBCATEGORIAS: 'Subcategorias',
  INSUMOS: 'Insumos',
  COMPRAS: 'Compras',
  PRODUTOS_FINAIS: 'ProdutosFinais',
  RECEITAS: 'Receitas',
  PRODUCAO: 'Producao',
  VENDAS: 'Vendas',
  FINANCEIRO: 'Financeiro'
};

/**
 * Retorna (criando se necessário) a planilha usada como banco de dados.
 * O ID fica salvo nas Propriedades do Script após a primeira execução de setupPlanilha().
 */
function getDb() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty('DB_SPREADSHEET_ID');
  if (id) {
    try {
      return SpreadsheetApp.openById(id);
    } catch (e) {
      // ID inválido/planilha removida: recria abaixo.
    }
  }
  var ss = SpreadsheetApp.create('Vendas_Financeiro - Banco de Dados');
  props.setProperty('DB_SPREADSHEET_ID', ss.getId());
  return ss;
}

function getSheet_(name) {
  var ss = getDb();
  var sheet = ss.getSheetByName(name);
  if (!sheet) throw new Error('Aba não encontrada: ' + name + '. Rode setupPlanilha() primeiro.');
  return sheet;
}

/** Lê todas as linhas de uma aba como array de objetos, usando a 1ª linha como cabeçalho. */
function readRows_(sheetName) {
  var sheet = getSheet_(sheetName);
  var values = sheet.getDataRange().getValues();
  if (values.length < 2) return [];
  var headers = values[0];
  var rows = [];
  for (var i = 1; i < values.length; i++) {
    var row = values[i];
    if (row.join('') === '') continue;
    var obj = {};
    for (var c = 0; c < headers.length; c++) {
      obj[headers[c]] = row[c];
    }
    obj._row = i + 1;
    rows.push(obj);
  }
  return rows;
}

/** Adiciona uma linha ao final de uma aba, respeitando a ordem das colunas do cabeçalho. */
function appendRow_(sheetName, obj) {
  var sheet = getSheet_(sheetName);
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var row = headers.map(function (h) {
    return obj[h] !== undefined ? obj[h] : '';
  });
  sheet.appendRow(row);
  return obj;
}

/** Atualiza uma linha existente (por número de linha) com os campos informados em obj. */
function updateRow_(sheetName, rowNumber, obj) {
  var sheet = getSheet_(sheetName);
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  headers.forEach(function (h, idx) {
    if (obj[h] !== undefined) {
      sheet.getRange(rowNumber, idx + 1).setValue(obj[h]);
    }
  });
}

function nextId_(sheetName) {
  var rows = readRows_(sheetName);
  var max = 0;
  rows.forEach(function (r) {
    var id = Number(r.id) || 0;
    if (id > max) max = id;
  });
  return max + 1;
}

function nowIso_() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss');
}

function todayStr_() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
}

/**
 * Verifica se o usuário logado com sua conta Google tem permissão de usar o app.
 * A lista de e-mails autorizados fica na aba "Usuarios".
 * O primeiro usuário a rodar setupPlanilha() é cadastrado automaticamente como admin.
 */
function getUsuarioAtual_() {
  var email = Session.getActiveUser().getEmail();
  if (!email) {
    throw new Error('Não foi possível identificar sua conta Google. Faça login para continuar.');
  }
  var usuarios = readRows_(SHEET_NAMES.USUARIOS);
  var usuario = usuarios.filter(function (u) { return String(u.email).toLowerCase() === email.toLowerCase(); })[0];
  if (!usuario) {
    throw new Error('Seu e-mail (' + email + ') não está autorizado a usar este aplicativo. Peça ao administrador para adicionar você na aba "Usuarios".');
  }
  if (String(usuario.ativo).toUpperCase() === 'FALSE') {
    throw new Error('Seu acesso foi desativado pelo administrador.');
  }
  return { email: email, nome: usuario.nome, papel: usuario.papel };
}

function exigirAdmin_() {
  var u = getUsuarioAtual_();
  if (u.papel !== 'admin') {
    throw new Error('Apenas administradores podem executar esta ação.');
  }
  return u;
}
