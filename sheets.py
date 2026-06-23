"""Экспорт результатов планового пересчёта в Google Sheets.

Каждая дата — отдельный лист (вкладка) в таблице. На листе два блока:
«Диллеры 10:55» и «Диллеры 18:55». Бот заполняет только:
  • колонку B — название роли (семьи);
  • колонку C «Количество участников на МП по войсу» — количество людей
    этой роли в войсе на момент пересчёта.
Остальные колонки (проценты, формулы) заполняются вручную.

Экспорт включается только если заданы переменные окружения:
  GOOGLE_SHEET_ID — ID Google-таблицы (часть URL между /d/ и /edit).
  GOOGLE_SA_JSON  — путь к JSON-ключу сервисного аккаунта Google
                    (по умолчанию service_account.json рядом с ботом).
Сервисный аккаунт должен иметь доступ Editor к таблице
(расшарьте таблицу на email вида ...@....iam.gserviceaccount.com).
"""
import os
import re
import asyncio

SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
SA_JSON = os.environ.get("GOOGLE_SA_JSON", "service_account.json")

# Время событий, по которым ведём отдельные блоки на листе
EVENT_TIMES = ["10:55", "18:55"]

# Фиксированный набор семей (ролей) и порядок строк на листе.
# Имена пишутся в таблицу как есть; счёт из войса сопоставляется с ролью
# Discord без учёта регистра. Семья без присутствия в войсе получает 0.
FAMILIES = [
    "Allegri",
    "Enemy",
    "Uzi",
    "Versetti",
    "Screamz",
    "Gachimov",
    "Vex",
    "Carbone",
    "Zangetsu",
    "Psychotropic",
    "Blade",
    "White",
    "Asgard",
    "Murazmatik",
    "Rehab",
    "Faraday",
]

# Раскладка листа (нумерация строк как в Google Sheets, с 1)
HEADER_ROW = 1
BLOCK_LABEL_ROW = {"10:55": 2, "18:55": 23}      # строка с меткой «Диллеры HH:MM»
BLOCK_FIRST_DATA_ROW = {"10:55": 3, "18:55": 24}  # первая строка с ролью/количеством

# Шапка (колонки A..I). A пустая — там у вас галочка.
HEADERS = [
    "",
    "Название семьи",
    "Количество участников \nна МП по войсу",
    "Процент\nот войса",
    "Общее \nколичество\nпо ВОЙСУ",
    "Сколько выпало\n семок",
    "Сколько выпало \nкустов",
    "Сколько выпало \nпакетиков",
    "Пакетики на фаму",
    "Сколько на выдачу\n семок",
    "Кусты на фаму",
]

# ---- Оформление (как в исходной таблице) ----
NCOL = 11                      # колонки A..K
COL_WIDTHS = [35, 150, 180, 140, 150, 150, 150, 150, 150, 150, 140]
CLR_HEAD = "F3F3F3"            # шапка — светло-серый
CLR_LIGHT = "CCCCCC"           # зебра, светлая строка
CLR_DARK = "B7B7B7"            # зебра тёмная + объединённые ячейки
CLR_BLACK = "000000"

# Индексы колонок (0-based)
(C_FLAG, C_NAME, C_COUNT, C_PCT, C_TOTAL, C_SEMKI, C_KUSTY,
 C_PAKET, C_PAKETFAM, C_VYD, C_KUSTYFAM) = range(11)

_gc = None        # кэш gspread-клиента
_enabled = None   # кэш результата проверки конфигурации


def is_enabled():
    """True, если задан ID таблицы и существует файл сервисного аккаунта."""
    global _enabled
    if _enabled is None:
        _enabled = bool(SHEET_ID) and os.path.exists(SA_JSON)
        if not _enabled:
            print("ℹ️  Google Sheets экспорт отключён "
                  "(нет GOOGLE_SHEET_ID или файла service_account.json).")
    return _enabled


def _client():
    """Ленивая инициализация gspread-клиента по сервисному аккаунту."""
    global _gc
    if _gc is None:
        import gspread  # импорт здесь, чтобы бот стартовал даже без пакета
        _gc = gspread.service_account(filename=SA_JSON)
    return _gc


def _rgb(hexs):
    h = hexs.lstrip("#")
    return {"red": int(h[0:2], 16) / 255,
            "green": int(h[2:4], 16) / 255,
            "blue": int(h[4:6], 16) / 255}


def _cellfmt(bg, numfmt=None):
    f = {"backgroundColor": _rgb(bg), "horizontalAlignment": "CENTER",
         "verticalAlignment": "MIDDLE", "wrapStrategy": "WRAP",
         "textFormat": {"bold": True, "fontFamily": "Roboto Serif"}}
    if numfmt:
        f["numberFormat"] = {"type": numfmt[0], "pattern": numfmt[1]}
    return f


def _build_template(ws):
    """Полностью оформляет новый лист: шапка, два блока, зебра, объединения,
    формулы, чекбоксы, закрепление шапки. Данные (кол-во) пишутся отдельно."""
    sid = ws.id
    thin = {"style": "SOLID", "color": _rgb(CLR_BLACK)}
    thick = {"style": "SOLID_THICK", "color": _rgb(CLR_BLACK)}

    def gr(r1, c1, r2, c2):
        return {"sheetId": sid, "startRowIndex": r1, "endRowIndex": r2,
                "startColumnIndex": c1, "endColumnIndex": c2}

    def repeat(rng, fmt, fields):
        return {"repeatCell": {"range": rng, "cell": {"userEnteredFormat": fmt},
                               "fields": fields}}

    def borders(rng, top=thin):
        return {"updateBorders": {"range": rng, "top": top, "bottom": thin,
                                  "left": thin, "right": thin,
                                  "innerHorizontal": thin, "innerVertical": thin}}

    F = ("userEnteredFormat(backgroundColor,horizontalAlignment,"
         "verticalAlignment,wrapStrategy,textFormat)")
    FNF = F + ",userEnteredFormat.numberFormat"
    nfam = len(FAMILIES)

    reqs = [
        # закрепляем первую строку
        {"updateSheetProperties": {"properties": {
            "sheetId": sid, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount"}},
    ]
    for i, w in enumerate(COL_WIDTHS):
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": w}, "fields": "pixelSize"}})

    # шапка
    reqs.append(repeat(gr(0, 0, 1, NCOL), _cellfmt(CLR_HEAD), F))
    reqs.append(borders(gr(0, 0, 1, NCOL), top=thick))

    for time_str in EVENT_TIMES:
        label = BLOCK_LABEL_ROW[time_str]
        first = BLOCK_FIRST_DATA_ROW[time_str]
        last = first + nfam - 1
        r1, r2 = first - 1, last         # 0-based начало, end-exclusive = last

        # метка «Диллеры HH:MM» (B:D объединены)
        reqs.append({"mergeCells": {"range": gr(label - 1, 1, label, 4),
                                    "mergeType": "MERGE_ALL"}})
        reqs.append(repeat(gr(label - 1, 1, label, 4), _cellfmt(CLR_DARK), F))
        reqs.append(borders(gr(label - 1, 1, label, 4)))

        # базовое оформление всего блока (жирный шрифт, центр, заливка, рамки)
        reqs.append(repeat(gr(r1, 0, r2, NCOL), _cellfmt(CLR_LIGHT), F))
        reqs.append(borders(gr(r1, 0, r2, NCOL)))
        # D — формат процента
        reqs.append(repeat(gr(r1, C_PCT, r2, C_PCT + 1),
                           _cellfmt(CLR_LIGHT, numfmt=("PERCENT", "0%")), FNF))
        # E (сумма) и F,G,H (выпало семок/кустов/пакетиков) — объединяем
        # напротив всех семей, тёмная заливка
        for col in (C_TOTAL, C_SEMKI, C_KUSTY, C_PAKET):
            reqs.append({"mergeCells": {"range": gr(r1, col, r2, col + 1),
                                        "mergeType": "MERGE_ALL"}})
            reqs.append(repeat(gr(r1, col, r2, col + 1),
                               _cellfmt(CLR_DARK, numfmt=("NUMBER", "0")), FNF))
            reqs.append(borders(gr(r1, col, r2, col + 1)))
        # чекбоксы в A
        reqs.append({"setDataValidation": {"range": gr(r1, 0, r2, 1),
            "rule": {"condition": {"type": "BOOLEAN"}, "strict": True,
                     "showCustomUi": True}}})
        # зебра: построчные колонки (A-D и формульные I,J,K). Объединённые
        # E,F,G,H остаются сплошными тёмными.
        for r in range(first, last + 1):
            bg = CLR_LIGHT if (r - first) % 2 == 0 else CLR_DARK
            for (a, b) in ((0, C_PCT + 1), (C_PAKETFAM, NCOL)):
                reqs.append({"repeatCell": {"range": gr(r - 1, a, r, b),
                    "cell": {"userEnteredFormat": {"backgroundColor": _rgb(bg)}},
                    "fields": "userEnteredFormat.backgroundColor"}})

    ws.spreadsheet.batch_update({"requests": reqs})

    # Текст и формулы (USER_ENTERED, чтобы формулы распознавались; локаль ru → ';')
    payload = [{"range": "A1", "values": [HEADERS]}]
    for time_str in EVENT_TIMES:
        label = BLOCK_LABEL_ROW[time_str]
        first = BLOCK_FIRST_DATA_ROW[time_str]
        last = first + nfam - 1
        payload.append({"range": f"B{label}", "values": [[f"Диллеры {time_str}"]]})
        payload.append({"range": f"B{first}:B{last}",
                        "values": [[n] for n in FAMILIES]})
        L = lambda i: chr(ord("A") + i)              # индекс колонки -> буква
        Lcount, Ltot = L(C_COUNT), L(C_TOTAL)
        # E = сумма «по войсу»; D = процент от войса
        payload.append({"range": f"{Ltot}{first}",
                        "values": [[f"=SUM({Lcount}{first}:{Lcount}{last})"]]})
        payload.append({"range": f"{L(C_PCT)}{first}:{L(C_PCT)}{last}",
                        "values": [[f"=IFERROR({Lcount}{r}/${Ltot}${first};0)"]
                                   for r in range(first, last + 1)]})
        # Раздача по семьям (формула_колонка, источник_общего):
        #   пакетики на фаму ← выпало пакетиков; на выдачу семок ← выпало семок;
        #   кусты на фаму ← выпало кустов. Делится между семьями с войсом >=10.
        for fcol, tcol in ((C_PAKETFAM, C_PAKET), (C_VYD, C_SEMKI),
                           (C_KUSTYFAM, C_KUSTY)):
            payload.append({"range": f"{L(fcol)}{first}:{L(fcol)}{last}",
                "values": [[f'=IF({Lcount}{r}<10;0;ROUND(${L(tcol)}${first}'
                            f'*{Lcount}{r}/SUMIF({Lcount}{first}:{Lcount}{last};'
                            f'">=10");0))'] for r in range(first, last + 1)]})
    ws.batch_update(payload, value_input_option="USER_ENTERED")


def _sync_update(date_str, time_str, rows):
    """Блокирующая запись в таблицу. rows: список (role_name, count).

    Создаёт оформленный лист при отсутствии и вписывает количество (колонка C).
    """
    import gspread

    gc = _client()
    sh = gc.open_by_key(SHEET_ID)

    try:
        ws = sh.worksheet(date_str)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=date_str, rows=50, cols=12)
        _build_template(ws)

    # Данные: B = семья, C = количество в войсе (имена дублируем для надёжности)
    first = BLOCK_FIRST_DATA_ROW[time_str]
    values = [[name, count] for name, count in rows]
    if values:
        last = first + len(values) - 1
        ws.update(range_name=f"B{first}:C{last}", values=values,
                  value_input_option="USER_ENTERED")

    return f"{date_str} / {time_str}: записано ролей — {len(values)}"


# ============ СВОДНЫЙ ЛИСТ «ИНФО» ============
# Первый лист таблицы. По каждой семье — сколько получено из доступного
# по трём ресурсам. «Доступно» — раздача семье (колонки I/J/K на листах-датах),
# «получено» — та же раздача, если на листе-дате стоит галочка (колонка A).
INFO_TITLE = "ИНФО"

# (подпись, буква колонки раздачи на листах-датах)
INFO_RESOURCES = [
    ("Семки", chr(ord("A") + C_VYD)),        # J — «на выдачу семок»
    ("Кусты", chr(ord("A") + C_KUSTYFAM)),   # K — «кусты на фаму»
    ("Пакетики", chr(ord("A") + C_PAKETFAM)),  # I — «пакетики на фаму»
]


def _is_date_title(title):
    """Лист-дата вида ДД.ММ (всё прочее, включая ИНФО, не учитываем)."""
    return bool(re.fullmatch(r"\d{2}\.\d{2}", title or ""))


def _sync_rebuild_info():
    """Создаёт/обновляет лист ИНФО и ставит его первым. Идемпотентна."""
    import gspread

    gc = _client()
    sh = gc.open_by_key(SHEET_ID)

    date_titles = [ws.title for ws in sh.worksheets() if _is_date_title(ws.title)]
    ncols = 1 + 2 * len(INFO_RESOURCES)

    try:
        info = sh.worksheet(INFO_TITLE)
    except gspread.WorksheetNotFound:
        info = sh.add_worksheet(title=INFO_TITLE, rows=len(FAMILIES) + 5, cols=ncols)

    # ИНФО всегда первым листом
    others = [ws for ws in sh.worksheets() if ws.title != INFO_TITLE]
    sh.reorder_worksheets([info] + others)

    first10 = BLOCK_FIRST_DATA_ROW["10:55"]
    first18 = BLOCK_FIRST_DATA_ROW["18:55"]

    header = ["Семья"]
    for label, _ in INFO_RESOURCES:
        header += [f"{label}\nполучено", f"{label}\nдоступно"]

    matrix = [header]
    for i, fam in enumerate(FAMILIES):
        r10, r18 = first10 + i, first18 + i
        row = [fam]
        for _, col in INFO_RESOURCES:
            if date_titles:
                # получено: раздача * галочка (TRUE=1 / FALSE=0) по обоим блокам
                received = "=" + "+".join(
                    f"'{d}'!A{r10}*'{d}'!{col}{r10}+'{d}'!A{r18}*'{d}'!{col}{r18}"
                    for d in date_titles
                )
                # доступно: вся раздача по обоим блокам
                available = "=" + "+".join(
                    f"'{d}'!{col}{r10}+'{d}'!{col}{r18}" for d in date_titles
                )
            else:
                received = available = 0
            row += [received, available]
        matrix.append(row)

    last_col = chr(ord("A") + ncols - 1)
    info.update(range_name=f"A1:{last_col}{len(matrix)}",
                values=matrix, value_input_option="USER_ENTERED")

    # Оформление: жирная шапка, жирная колонка семей, закрепления, ширины
    sid = info.id
    F = ("userEnteredFormat(backgroundColor,horizontalAlignment,"
         "verticalAlignment,wrapStrategy,textFormat)")
    reqs = [
        {"updateSheetProperties": {"properties": {
            "sheetId": sid,
            "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 1}},
            "fields": ("gridProperties.frozenRowCount,"
                       "gridProperties.frozenColumnCount")}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": ncols},
            "cell": {"userEnteredFormat": _cellfmt(CLR_HEAD)}, "fields": F}},
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 1,
                      "endRowIndex": len(FAMILIES) + 1,
                      "startColumnIndex": 0, "endColumnIndex": 1},
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True, "fontFamily": "Roboto Serif"}}},
            "fields": "userEnteredFormat.textFormat"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 150}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": 1, "endIndex": ncols},
            "properties": {"pixelSize": 110}, "fields": "pixelSize"}},
    ]
    sh.batch_update({"requests": reqs})

    return (f"ИНФО обновлён: семей {len(FAMILIES)}, "
            f"листов учтено {len(date_titles)}")


async def rebuild_info():
    """Пересобрать сводный лист ИНФО (в отдельном потоке)."""
    if not is_enabled():
        return None
    return await asyncio.to_thread(_sync_rebuild_info)


async def update_event(date_str, time_str, role_counts, role_order=None):
    """Записать снимок пересчёта в Google Sheets (в отдельном потоке).

    date_str   — имя листа, напр. '17.06'.
    time_str   — '10:55' или '18:55'.
    role_counts — dict {имя_роли: количество_в_войсе}.
    role_order  — список имён семей для порядка строк; если None — берём
                  фиксированный список FAMILIES.
    """
    if not is_enabled():
        return None
    if time_str not in BLOCK_LABEL_ROW:
        return None

    order = role_order or FAMILIES
    order_lc = {str(n).strip().lower() for n in order}

    # Сопоставляем счёт из войса с семьёй без учёта регистра
    lc = {}
    for name, count in role_counts.items():
        key = str(name).strip().lower()
        lc[key] = lc.get(key, 0) + count

    rows = [(name, lc.get(name.strip().lower(), 0)) for name in order]

    # Роли с людьми в войсе, которых нет в фиксированном списке семей,
    # — чтобы такие расхождения не терялись молча.
    unmatched = sorted(
        str(name) for name, count in role_counts.items()
        if count and str(name).strip().lower() not in order_lc
    )

    result = await asyncio.to_thread(_sync_update, date_str, time_str, rows)

    # Пересобираем сводный лист ИНФО, чтобы учесть этот (возможно новый) лист-дату
    try:
        await asyncio.to_thread(_sync_rebuild_info)
    except Exception as e:
        print(f"⚠️ Не удалось обновить лист ИНФО: {e}")

    if unmatched:
        result += " ⚠️ нет в списке семей: " + ", ".join(unmatched)
    return result
