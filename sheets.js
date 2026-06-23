// Экспорт результатов планового пересчёта в Google Sheets (googleapis).
//
// Каждая дата — отдельный лист. На листе два блока «Диллеры 10:55» и
// «Диллеры 18:55». Бот заполняет колонку B (роль/семья) и C (количество).
// Остальные колонки (проценты, формулы) — оформляются шаблоном.
//
// Включается, если заданы GOOGLE_SHEET_ID и существует файл GOOGLE_SA_JSON.
import fs from 'fs';
import { google } from 'googleapis';

const SHEET_ID = process.env.GOOGLE_SHEET_ID || '';
const SA_JSON = process.env.GOOGLE_SA_JSON || 'service_account.json';

// Время событий, по которым ведём отдельные блоки на листе
export const EVENT_TIMES = ['10:55', '18:55'];

// Фиксированный набор семей (ролей) и порядок строк на листе.
const FAMILIES = [
  'Allegri', 'Enemy', 'Uzi', 'Versetti', 'Screamz', 'Gachimov', 'Vex',
  'Carbone', 'Zangetsu', 'Psychotropic', 'Blade', 'White', 'Asgard',
  'Murazmatik', 'Rehab', 'Faraday',
];

// Раскладка листа (нумерация строк как в Google Sheets, с 1)
const BLOCK_LABEL_ROW = { '10:55': 2, '18:55': 23 };
const BLOCK_FIRST_DATA_ROW = { '10:55': 3, '18:55': 24 };

const HEADERS = [
  '', 'Название семьи', 'Количество участников \nна МП по войсу', 'Процент\nот войса',
  'Общее \nколичество\nпо ВОЙСУ', 'Сколько выпало\n семок', 'Сколько выпало \nкустов',
  'Сколько выпало \nпакетиков', 'Пакетики на фаму', 'Сколько на выдачу\n семок', 'Кусты на фаму',
];

const NCOL = 11; // колонки A..K
const COL_WIDTHS = [35, 150, 180, 140, 150, 150, 150, 150, 150, 150, 140];
const CLR_HEAD = 'F3F3F3';
const CLR_LIGHT = 'CCCCCC';
const CLR_DARK = 'B7B7B7';
const CLR_BLACK = '000000';

// Индексы колонок (0-based)
const C_NAME = 1, C_COUNT = 2, C_PCT = 3, C_TOTAL = 4, C_SEMKI = 5,
  C_KUSTY = 6, C_PAKET = 7, C_PAKETFAM = 8, C_VYD = 9, C_KUSTYFAM = 10;

const INFO_TITLE = 'ИНФО';
const L = (i) => String.fromCharCode('A'.charCodeAt(0) + i);
// (подпись, буква колонки раздачи на листах-датах)
const INFO_RESOURCES = [
  ['Семки', L(C_VYD)],
  ['Кусты', L(C_KUSTYFAM)],
  ['Пакетики', L(C_PAKETFAM)],
];

let _sheets = null;
let _enabled = null;

export function isEnabled() {
  if (_enabled === null) {
    _enabled = Boolean(SHEET_ID) && fs.existsSync(SA_JSON);
    if (!_enabled) {
      console.log('ℹ️  Google Sheets экспорт отключён (нет GOOGLE_SHEET_ID или файла service_account.json).');
    }
  }
  return _enabled;
}

async function api() {
  if (!_sheets) {
    const auth = new google.auth.GoogleAuth({
      keyFile: SA_JSON,
      scopes: ['https://www.googleapis.com/auth/spreadsheets'],
    });
    _sheets = google.sheets({ version: 'v4', auth: await auth.getClient() });
  }
  return _sheets;
}

function rgb(hexs) {
  const h = hexs.replace('#', '');
  return {
    red: parseInt(h.slice(0, 2), 16) / 255,
    green: parseInt(h.slice(2, 4), 16) / 255,
    blue: parseInt(h.slice(4, 6), 16) / 255,
  };
}

function cellfmt(bg, numfmt = null) {
  const f = {
    backgroundColor: rgb(bg), horizontalAlignment: 'CENTER', verticalAlignment: 'MIDDLE',
    wrapStrategy: 'WRAP', textFormat: { bold: true, fontFamily: 'Roboto Serif' },
  };
  if (numfmt) f.numberFormat = { type: numfmt[0], pattern: numfmt[1] };
  return f;
}

function buildTemplateRequests(sid) {
  const thin = { style: 'SOLID', color: rgb(CLR_BLACK) };
  const thick = { style: 'SOLID_THICK', color: rgb(CLR_BLACK) };
  const gr = (r1, c1, r2, c2) => ({ sheetId: sid, startRowIndex: r1, endRowIndex: r2, startColumnIndex: c1, endColumnIndex: c2 });
  const repeat = (range, cellFmt, fields) => ({ repeatCell: { range, cell: { userEnteredFormat: cellFmt }, fields } });
  const borders = (range, top = thin) => ({ updateBorders: { range, top, bottom: thin, left: thin, right: thin, innerHorizontal: thin, innerVertical: thin } });

  const F = 'userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,wrapStrategy,textFormat)';
  const FNF = F + ',userEnteredFormat.numberFormat';
  const nfam = FAMILIES.length;

  const reqs = [
    { updateSheetProperties: { properties: { sheetId: sid, gridProperties: { frozenRowCount: 1 } }, fields: 'gridProperties.frozenRowCount' } },
  ];
  COL_WIDTHS.forEach((w, i) => {
    reqs.push({ updateDimensionProperties: { range: { sheetId: sid, dimension: 'COLUMNS', startIndex: i, endIndex: i + 1 }, properties: { pixelSize: w }, fields: 'pixelSize' } });
  });

  reqs.push(repeat(gr(0, 0, 1, NCOL), cellfmt(CLR_HEAD), F));
  reqs.push(borders(gr(0, 0, 1, NCOL), thick));

  for (const timeStr of EVENT_TIMES) {
    const label = BLOCK_LABEL_ROW[timeStr];
    const first = BLOCK_FIRST_DATA_ROW[timeStr];
    const last = first + nfam - 1;
    const r1 = first - 1, r2 = last;

    reqs.push({ mergeCells: { range: gr(label - 1, 1, label, 4), mergeType: 'MERGE_ALL' } });
    reqs.push(repeat(gr(label - 1, 1, label, 4), cellfmt(CLR_DARK), F));
    reqs.push(borders(gr(label - 1, 1, label, 4)));

    reqs.push(repeat(gr(r1, 0, r2, NCOL), cellfmt(CLR_LIGHT), F));
    reqs.push(borders(gr(r1, 0, r2, NCOL)));
    reqs.push(repeat(gr(r1, C_PCT, r2, C_PCT + 1), cellfmt(CLR_LIGHT, ['PERCENT', '0%']), FNF));

    for (const col of [C_TOTAL, C_SEMKI, C_KUSTY, C_PAKET]) {
      reqs.push({ mergeCells: { range: gr(r1, col, r2, col + 1), mergeType: 'MERGE_ALL' } });
      reqs.push(repeat(gr(r1, col, r2, col + 1), cellfmt(CLR_DARK, ['NUMBER', '0']), FNF));
      reqs.push(borders(gr(r1, col, r2, col + 1)));
    }

    reqs.push({ setDataValidation: { range: gr(r1, 0, r2, 1), rule: { condition: { type: 'BOOLEAN' }, strict: true, showCustomUi: true } } });

    for (let r = first; r <= last; r++) {
      const bg = (r - first) % 2 === 0 ? CLR_LIGHT : CLR_DARK;
      for (const [a, b] of [[0, C_PCT + 1], [C_PAKETFAM, NCOL]]) {
        reqs.push({ repeatCell: { range: gr(r - 1, a, r, b), cell: { userEnteredFormat: { backgroundColor: rgb(bg) } }, fields: 'userEnteredFormat.backgroundColor' } });
      }
    }
  }
  return reqs;
}

function buildTemplateValues(title) {
  const q = (a1) => `'${title}'!${a1}`;
  const nfam = FAMILIES.length;
  const data = [{ range: q('A1'), values: [HEADERS] }];

  for (const timeStr of EVENT_TIMES) {
    const label = BLOCK_LABEL_ROW[timeStr];
    const first = BLOCK_FIRST_DATA_ROW[timeStr];
    const last = first + nfam - 1;
    data.push({ range: q(`B${label}`), values: [[`Диллеры ${timeStr}`]] });
    data.push({ range: q(`B${first}:B${last}`), values: FAMILIES.map((n) => [n]) });

    const Lcount = L(C_COUNT), Ltot = L(C_TOTAL);
    data.push({ range: q(`${Ltot}${first}`), values: [[`=SUM(${Lcount}${first}:${Lcount}${last})`]] });

    const pctRows = [];
    for (let r = first; r <= last; r++) pctRows.push([`=IFERROR(${Lcount}${r}/$${Ltot}$${first};0)`]);
    data.push({ range: q(`${L(C_PCT)}${first}:${L(C_PCT)}${last}`), values: pctRows });

    for (const [fcol, tcol] of [[C_PAKETFAM, C_PAKET], [C_VYD, C_SEMKI], [C_KUSTYFAM, C_KUSTY]]) {
      const rows = [];
      for (let r = first; r <= last; r++) {
        rows.push([`=IF(${Lcount}${r}<10;0;ROUND($${L(tcol)}$${first}*${Lcount}${r}/SUMIF(${Lcount}${first}:${Lcount}${last};">=10");0))`]);
      }
      data.push({ range: q(`${L(fcol)}${first}:${L(fcol)}${last}`), values: rows });
    }
  }
  return data;
}

async function getSheetsMeta() {
  const sheets = await api();
  const res = await sheets.spreadsheets.get({ spreadsheetId: SHEET_ID, fields: 'sheets.properties(sheetId,title,index)' });
  return res.data.sheets.map((s) => s.properties);
}

async function ensureDateSheet(title) {
  const sheets = await api();
  const meta = await getSheetsMeta();
  const found = meta.find((p) => p.title === title);
  if (found) return found.sheetId;

  const add = await sheets.spreadsheets.batchUpdate({
    spreadsheetId: SHEET_ID,
    requestBody: { requests: [{ addSheet: { properties: { title, gridProperties: { rowCount: 50, columnCount: 12 } } } }] },
  });
  const sid = add.data.replies[0].addSheet.properties.sheetId;

  await sheets.spreadsheets.batchUpdate({ spreadsheetId: SHEET_ID, requestBody: { requests: buildTemplateRequests(sid) } });
  await sheets.spreadsheets.values.batchUpdate({ spreadsheetId: SHEET_ID, requestBody: { valueInputOption: 'USER_ENTERED', data: buildTemplateValues(title) } });
  return sid;
}

async function syncUpdate(dateStr, timeStr, rows) {
  const sheets = await api();
  await ensureDateSheet(dateStr);

  const first = BLOCK_FIRST_DATA_ROW[timeStr];
  const values = rows.map(([name, count]) => [name, count]);
  if (values.length) {
    const last = first + values.length - 1;
    await sheets.spreadsheets.values.update({
      spreadsheetId: SHEET_ID,
      range: `'${dateStr}'!B${first}:C${last}`,
      valueInputOption: 'USER_ENTERED',
      requestBody: { values },
    });
  }
  return `${dateStr} / ${timeStr}: записано ролей — ${values.length}`;
}

const isDateTitle = (title) => /^\d{2}\.\d{2}$/.test(title || '');

async function rebuildInfo() {
  const sheets = await api();
  let meta = await getSheetsMeta();
  const dateTitles = meta.filter((p) => isDateTitle(p.title)).map((p) => p.title);
  const ncols = 1 + 2 * INFO_RESOURCES.length;

  let info = meta.find((p) => p.title === INFO_TITLE);
  if (!info) {
    const add = await sheets.spreadsheets.batchUpdate({
      spreadsheetId: SHEET_ID,
      requestBody: { requests: [{ addSheet: { properties: { title: INFO_TITLE, gridProperties: { rowCount: FAMILIES.length + 5, columnCount: ncols } } } }] },
    });
    info = add.data.replies[0].addSheet.properties;
  }
  const sid = info.sheetId;

  // ИНФО всегда первым листом
  await sheets.spreadsheets.batchUpdate({
    spreadsheetId: SHEET_ID,
    requestBody: { requests: [{ updateSheetProperties: { properties: { sheetId: sid, index: 0 }, fields: 'index' } }] },
  });

  const first10 = BLOCK_FIRST_DATA_ROW['10:55'];
  const first18 = BLOCK_FIRST_DATA_ROW['18:55'];

  const header = ['Семья'];
  for (const [label] of INFO_RESOURCES) header.push(`${label}\nполучено`, `${label}\nдоступно`);

  const matrix = [header];
  FAMILIES.forEach((fam, i) => {
    const r10 = first10 + i, r18 = first18 + i;
    const row = [fam];
    for (const [, col] of INFO_RESOURCES) {
      let received = 0, available = 0;
      if (dateTitles.length) {
        received = '=' + dateTitles.map((d) => `'${d}'!A${r10}*'${d}'!${col}${r10}+'${d}'!A${r18}*'${d}'!${col}${r18}`).join('+');
        available = '=' + dateTitles.map((d) => `'${d}'!${col}${r10}+'${d}'!${col}${r18}`).join('+');
      }
      row.push(received, available);
    }
    matrix.push(row);
  });

  const lastCol = L(ncols - 1);
  await sheets.spreadsheets.values.update({
    spreadsheetId: SHEET_ID,
    range: `'${INFO_TITLE}'!A1:${lastCol}${matrix.length}`,
    valueInputOption: 'USER_ENTERED',
    requestBody: { values: matrix },
  });

  const F = 'userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,wrapStrategy,textFormat)';
  const reqs = [
    { updateSheetProperties: { properties: { sheetId: sid, gridProperties: { frozenRowCount: 1, frozenColumnCount: 1 } }, fields: 'gridProperties.frozenRowCount,gridProperties.frozenColumnCount' } },
    { repeatCell: { range: { sheetId: sid, startRowIndex: 0, endRowIndex: 1, startColumnIndex: 0, endColumnIndex: ncols }, cell: { userEnteredFormat: cellfmt(CLR_HEAD) }, fields: F } },
    { repeatCell: { range: { sheetId: sid, startRowIndex: 1, endRowIndex: FAMILIES.length + 1, startColumnIndex: 0, endColumnIndex: 1 }, cell: { userEnteredFormat: { textFormat: { bold: true, fontFamily: 'Roboto Serif' } } }, fields: 'userEnteredFormat.textFormat' } },
    { updateDimensionProperties: { range: { sheetId: sid, dimension: 'COLUMNS', startIndex: 0, endIndex: 1 }, properties: { pixelSize: 150 }, fields: 'pixelSize' } },
    { updateDimensionProperties: { range: { sheetId: sid, dimension: 'COLUMNS', startIndex: 1, endIndex: ncols }, properties: { pixelSize: 110 }, fields: 'pixelSize' } },
  ];
  await sheets.spreadsheets.batchUpdate({ spreadsheetId: SHEET_ID, requestBody: { requests: reqs } });

  return `ИНФО обновлён: семей ${FAMILIES.length}, листов учтено ${dateTitles.length}`;
}

export async function updateEvent(dateStr, timeStr, roleCounts, roleOrder = null) {
  // Записать снимок пересчёта в Google Sheets.
  if (!isEnabled()) return null;
  if (!(timeStr in BLOCK_LABEL_ROW)) return null;

  const order = roleOrder || FAMILIES;
  const orderLc = new Set(order.map((n) => String(n).trim().toLowerCase()));

  const lc = {};
  for (const [name, count] of Object.entries(roleCounts)) {
    const key = String(name).trim().toLowerCase();
    lc[key] = (lc[key] || 0) + count;
  }

  const rows = order.map((name) => [name, lc[String(name).trim().toLowerCase()] || 0]);

  const unmatched = Object.entries(roleCounts)
    .filter(([name, count]) => count && !orderLc.has(String(name).trim().toLowerCase()))
    .map(([name]) => String(name))
    .sort();

  let result = await syncUpdate(dateStr, timeStr, rows);

  try {
    await rebuildInfo();
  } catch (e) {
    console.log(`⚠️ Не удалось обновить лист ИНФО: ${e.message}`);
  }

  if (unmatched.length) result += ' ⚠️ нет в списке семей: ' + unmatched.join(', ');
  return result;
}
