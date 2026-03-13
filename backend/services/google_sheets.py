"""
Сервіс для роботи з Google Sheets: отримання листів, даних, визначення рядка заголовків та мапінгу колонок.
"""
import re
import os
from typing import Any
from urllib.parse import quote

try:
    import requests
except ImportError:
    requests = None

from services.parser import (
    normalize_url,
    parse_position,
    parse_volume,
    is_date_like,
)

# Кандидати назв колонок для авто-визначення
URL_CANDIDATES = [
    "relevant url", "url", "target url", "landing", "page", "сторінка",
    "цільова сторінка", "landing page", "target page", "підкатегорія",
    "фільтр х1", "фільтр х2"  # Avrora: URL може бути в цих колонках
]
KEYWORD_CANDIDATES = [
    "keywords", "keyword", "ключові слова", "ключ", "query", "запит",
    "ключевое слово", "ключове слово", "значення фільтру"  # Avrora
]
VOLUME_CANDIDATES = [
    "частота", "frequency", "volume", "search volume", "sv", "traffic",
    "запитів", "monthly searches", "monthly_searches", "частотность"
]
CATEGORY_CANDIDATES = ["категорія", "category"]

# Мінімальний бал для визначення рядка заголовків
MIN_HEADER_SCORE = 5

# Колонки A–M (індекси 0–12) — діапазон пошуку URL, Keyword, Volume, Category
HEADER_SEARCH_MAX_COL = 13


def _get_api_key() -> str | None:
    return os.environ.get("GOOGLE_SHEETS_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _extract_spreadsheet_id(url: str) -> str | None:
    """Витягує spreadsheet ID з URL Google Sheets."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    # https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit...
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    return match.group(1) if match else None


def _extract_gid_from_url(url: str) -> str | None:
    """Витягує gid листа з URL (якщо є)."""
    if not url:
        return None
    match = re.search(r"[?&]gid=(\d+)", url)
    return match.group(1) if match else None


def fetch_sheets_list(spreadsheet_url: str) -> list[dict]:
    """
    Отримує список листів таблиці через Google Sheets API.
    Повертає [{"id": sheetId, "title": "..."}, ...]
    """
    if not requests:
        raise RuntimeError("Потрібна бібліотека requests: pip install requests")
    api_key = _get_api_key()
    if not api_key:
        raise ValueError(
            "Для доступу до Google Sheets встановіть змінну середовища GOOGLE_SHEETS_API_KEY або GOOGLE_API_KEY. "
            "Отримати ключ: https://console.cloud.google.com/apis/credentials"
        )
    sheet_id = _extract_spreadsheet_id(spreadsheet_url)
    if not sheet_id:
        raise ValueError("Невірний URL Google Таблиці")

    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
    resp = requests.get(url, params={"key": api_key}, timeout=15)
    if not resp.ok:
        err = resp.json().get("error", {})
        msg = err.get("message", resp.text)
        raise ValueError(f"Помилка Google Sheets API: {msg}")

    data = resp.json()
    sheets = []
    for s in data.get("sheets", []):
        props = s.get("properties", {})
        sheets.append({
            "id": props.get("sheetId"),
            "title": props.get("title", "Лист"),
        })
    return sheets


def fetch_sheet_data(spreadsheet_url: str, sheet_id: int | str, range_a1: str | None = None) -> list[list]:
    """
    Отримує дані листа. Якщо range_a1 не вказано — завантажує A1:ZZ1000.
    sheet_id: числовий id листа або назва листа (title).
    Повертає список рядків (list of list).
    """
    if not requests:
        raise RuntimeError("Потрібна бібліотека requests: pip install requests")
    api_key = _get_api_key()
    if not api_key:
        raise ValueError("Встановіть GOOGLE_SHEETS_API_KEY")

    spreadsheet_id = _extract_spreadsheet_id(spreadsheet_url)
    if not spreadsheet_id:
        raise ValueError("Невірний URL Google Таблиці")

    if range_a1:
        range_str = range_a1
    else:
        # sheet_id може бути числом (gid) або назвою листа
        if isinstance(sheet_id, str) and not str(sheet_id).isdigit():
            sheet_title = sheet_id
        else:
            sheet_title = _get_sheet_title_by_id(spreadsheet_id, sheet_id, api_key)
        # Екранування одинарних лапок у назві листа (A1 notation)
        sheet_title_escaped = str(sheet_title).replace("'", "''")
        range_str = f"'{sheet_title_escaped}'!A1:ZZ1000"

    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{quote(range_str, safe='')}"
    # FORMATTED_VALUE — заголовки дат як "2025-08-05", не як число
    resp = requests.get(url, params={"key": api_key, "valueRenderOption": "FORMATTED_VALUE"}, timeout=30)
    if not resp.ok:
        err = resp.json().get("error", {})
        raise ValueError(err.get("message", resp.text))

    values = resp.json().get("values", [])
    # Нормалізуємо довжину рядків (Sheets може повертати різну кількість комірок)
    max_cols = max(len(row) if isinstance(row, (list, tuple)) else 0 for row in values) if values else 0
    result = []
    for row in values:
        if not isinstance(row, (list, tuple)):
            row = [row] if row is not None else []
        padded = list(row) + [""] * (max_cols - len(row))
        result.append(["" if c is None else str(c).strip() for c in padded])
    return result


def _get_sheet_title_by_id(spreadsheet_id: str, sheet_id: int | str, api_key: str) -> str:
    """Отримує назву листа за sheetId (gid з URL)."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
    resp = requests.get(url, params={"key": api_key}, timeout=15)
    if not resp.ok:
        raise ValueError(f"Не вдалося отримати метадані таблиці: {resp.json().get('error', {}).get('message', resp.text)}")
    data = resp.json()
    sheet_id_str = str(sheet_id)
    for s in data.get("sheets", []):
        props = s.get("properties", {})
        sid = props.get("sheetId")
        if str(sid) == sheet_id_str:
            title = props.get("title")
            if title:
                return title
            return sheet_id_str
    raise ValueError(f"Лист з id {sheet_id} не знайдено в таблиці")


def _find_matching_column_index(
    row: list,
    candidates: list[str],
    max_col: int | None = None,
) -> int | None:
    """
    Повертає індекс колонки, що збігається з одним із кандидатів.
    max_col: обмеження пошуку колонками 0..max_col-1 (A..M для max_col=13). None = всі колонки.
    """
    limit = max_col if max_col is not None else len(row)
    for i, cell in enumerate(row):
        if i >= limit:
            break
        val = str(cell).strip().lower()
        if not val:
            continue
        for c in candidates:
            if c in val or val in c:
                return i
    return None


def _is_date_like_header(val: Any) -> bool:
    """Перевірка, чи значення виглядає як дата (назва колонки). Приймає str або number (serial date)."""
    if val is None:
        return False
    val = str(val).strip()
    if not val:
        return False
    if re.match(r"^\d{4}-\d{2}-\d{2}$", val):
        return True
    if re.match(r"^\d{2}\.\d{2}\.\d{4}$", val):
        return True
    if re.match(r"^\d{2}/\d{2}/\d{4}$", val):
        return True
    if re.match(r"^\d{2}-\d{2}-\d{2}$", val):
        return True
    # Serial date (Google Sheets) — число 40000–50000
    try:
        n = float(val)
        if 30000 < n < 60000:
            return True
    except ValueError:
        pass
    try:
        import pandas as pd
        pd.to_datetime(val, dayfirst=True)
        return True
    except Exception:
        pass
    return False


def _looks_like_number(val: str) -> bool:
    """Чи виглядає значення як число (позиція, volume)."""
    if not val or not isinstance(val, str):
        return False
    val = val.strip()
    if not val:
        return False
    try:
        n = float(val.replace(",", "").replace(" ", ""))
        return isinstance(n, (int, float)) and (n == int(n) or abs(n - int(n)) > 0)
    except ValueError:
        return False


def _looks_like_url(val: str) -> bool:
    return bool(val and ("http" in val.lower() or val.startswith("www.")))


def _looks_like_data_row(
    row: list,
    url_col: int,
    kw_col: int,
    date_cols: list[int],
    all_rows: list[list],
    header_row_idx: int,
) -> bool:
    """Перевіряє, чи рядок виглядає як рядок даних (а не заголовки)."""
    if not row or url_col >= len(row) or kw_col >= len(row):
        return False
    url_val = str(row[url_col] if url_col < len(row) else "").strip()
    kw_val = str(row[kw_col] if kw_col < len(row) else "").strip()
    if not url_val and not kw_val:
        return False
    # URL-подібне або текст у keyword
    has_url_like = _looks_like_url(url_val)
    has_kw = len(kw_val) > 1
    # У колонках дат — числа 1-101
    date_vals_ok = 0
    for dc in date_cols:
        if dc < len(row):
            v = str(row[dc]).strip()
            if v and _looks_like_number(v):
                try:
                    n = int(float(v))
                    if 1 <= n <= 101:
                        date_vals_ok += 1
                except ValueError:
                    pass
    return (has_url_like or has_kw) and (date_vals_ok >= 1 or len(date_cols) == 0)


def _score_header_row(
    row: list,
    url_col: int,
    kw_col: int,
    date_cols: list[int],
    r: int,
    rows_to_check: list[list],
) -> int:
    """Обчислює бал рядка як заголовків."""
    score = 6  # URL + Keyword
    if _find_matching_column_index(row, VOLUME_CANDIDATES, HEADER_SEARCH_MAX_COL) is not None:
        score += 1
    if _find_matching_column_index(row, CATEGORY_CANDIDATES, HEADER_SEARCH_MAX_COL) is not None:
        score += 1
    score += 2 * min(len(date_cols), 10)
    numeric_count = sum(1 for c in row if _looks_like_number(str(c)))
    if numeric_count > len(row) * 0.5:
        score -= 2
    if r + 1 < len(rows_to_check):
        next_row = rows_to_check[r + 1]
        if len(next_row) >= max([url_col, kw_col] + date_cols):
            if _looks_like_data_row(next_row, url_col, kw_col, date_cols, rows_to_check, r):
                score += 1
    return score


def find_header_row(rows: list[list], max_rows: int = 50) -> int:
    """
    Шукає рядок заголовків у перших max_rows рядках.
    Повертає 0-based індекс рядка або -1.
    """
    rows_to_check = rows[:max_rows]
    if not rows_to_check:
        return -1

    best_row = -1
    best_score = -1

    for r in range(len(rows_to_check)):
        row = rows_to_check[r]
        if not row or not isinstance(row, (list, tuple)):
            continue

        # URL, Keyword — спочатку в A–M, потім у всіх колонках
        url_col = _find_matching_column_index(row, URL_CANDIDATES, HEADER_SEARCH_MAX_COL)
        kw_col = _find_matching_column_index(row, KEYWORD_CANDIDATES, HEADER_SEARCH_MAX_COL)
        if url_col is None or kw_col is None:
            url_col = _find_matching_column_index(row, URL_CANDIDATES, None)
            kw_col = _find_matching_column_index(row, KEYWORD_CANDIDATES, None)
        if url_col is None or kw_col is None:
            continue

        # Колонки з датами — перевіряємо всі колонки
        date_cols = [i for i, cell in enumerate(row) if _is_date_like_header(cell)]
        if not date_cols:
            continue

        score = _score_header_row(row, url_col, kw_col, date_cols, r, rows_to_check)

        if score > best_score and score >= MIN_HEADER_SCORE:
            best_score = score
            best_row = r

    return best_row


def suggest_column_mapping(headers: list[str]) -> dict[str, Any]:
    """
    Пропонує мапінг колонок на основі заголовків.
    URL, Keyword, Volume, Category — тільки з колонок A–M (індекси 0..12).
    date_columns — з усіх колонок.
    """
    mapping = {"url": None, "keyword": None, "volume": None, "category": None, "date_columns": []}
    if not isinstance(headers, (list, tuple)):
        return mapping
    headers_for_struct = headers[:HEADER_SEARCH_MAX_COL]
    headers_lower = {h.strip().lower(): h.strip() for h in headers_for_struct if h and str(h).strip()}

    for cand_list, key in [
        (URL_CANDIDATES, "url"),
        (KEYWORD_CANDIDATES, "keyword"),
        (VOLUME_CANDIDATES, "volume"),
        (CATEGORY_CANDIDATES, "category"),
    ]:
        for cand in cand_list:
            for hl, orig in headers_lower.items():
                if cand in hl or hl in cand:
                    mapping[key] = orig
                    break
            if mapping[key]:
                break

    for h in headers:
        h_str = str(h).strip()
        if h_str and _is_date_like_header(h_str):
            mapping["date_columns"].append(h_str)

    return mapping


def normalize_date_header(date_str: str) -> str:
    """Нормалізує дату заголовка до YYYY-MM-DD для консистентності."""
    if not date_str:
        return ""
    try:
        import pandas as pd
        dt = pd.to_datetime(date_str.strip(), dayfirst=True)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return date_str


def parse_positions_from_rows(
    rows: list[list],
    header_row_index: int,
    column_mapping: dict[str, Any],
) -> list[dict]:
    """
    Парсить рядки в список позицій (формат як parse_positions_file).
    column_mapping: {"url": "Relevant URL", "keyword": "Keywords", "volume": "Частота", "date_columns": ["04.02.2025", ...]}
    """
    if header_row_index < 0 or header_row_index >= len(rows):
        raise ValueError("Невірний індекс рядка заголовків")

    headers = rows[header_row_index]
    data_rows = rows[header_row_index + 1:]

    url_col = column_mapping.get("url")
    keyword_col = column_mapping.get("keyword")
    volume_col = column_mapping.get("volume")
    date_columns = column_mapping.get("date_columns")
    if not isinstance(date_columns, (list, tuple)):
        date_columns = []

    if not url_col or not keyword_col:
        raise ValueError("Обов'язкові колонки URL та Keyword")

    # Індекси колонок
    header_to_idx = {str(h).strip(): i for i, h in enumerate(headers) if h}
    url_idx = header_to_idx.get(str(url_col).strip())
    kw_idx = header_to_idx.get(str(keyword_col).strip())
    vol_idx = header_to_idx.get(str(volume_col).strip()) if volume_col else None
    date_idxs = [(header_to_idx.get(str(d).strip()), d) for d in date_columns if str(d).strip() in header_to_idx]
    date_idxs = [(i, d) for i, d in date_idxs if i is not None]

    if url_idx is None or kw_idx is None:
        raise ValueError("Колонки URL або Keyword не знайдено в заголовках")

    if not date_idxs:
        raise ValueError("Не знайдено колонок з датами позицій")

    results = []
    for row in data_rows:
        if len(row) <= max(url_idx, kw_idx):
            continue
        url = normalize_url(str(row[url_idx]))
        keyword = str(row[kw_idx]).strip()
        if not url or not keyword:
            continue

        positions = {}
        for idx, date_header in date_idxs:
            if idx < len(row):
                val = row[idx]
                pos = parse_position(val)
                if pos is not None:
                    norm_date = normalize_date_header(date_header) or date_header
                    positions[norm_date] = pos

        if not positions:
            continue

        item = {"url": url, "keyword": keyword, "positions": positions}
        if vol_idx is not None and vol_idx < len(row):
            vol = parse_volume(row[vol_idx])
            if vol is not None:
                item["volume"] = vol
        results.append(item)

    return results


def get_preview_data(
    spreadsheet_url: str,
    sheet_id: int | str,
) -> dict:
    """
    Завантажує дані, визначає рядок заголовків, пропонує мапінг.
    Повертає: {headers, header_row_index, sample_rows, suggested_mapping, all_headers}
    """
    rows = fetch_sheet_data(spreadsheet_url, sheet_id, None)
    # Обмежуємо для preview — достатньо 100 рядків для аналізу
    rows = rows[:100]

    header_row = find_header_row(rows)
    if header_row < 0:
        raise ValueError("Не вдалося визначити рядок заголовків у перших 50 рядках. Перевірте структуру таблиці.")

    headers = rows[header_row]
    suggested_mapping = suggest_column_mapping(headers)
    sample_rows = rows[header_row : header_row + 6]  # заголовки + 5 рядків даних

    return {
        "headers": headers,
        "header_row_index": header_row,
        "sample_rows": sample_rows,
        "suggested_mapping": suggested_mapping,
        "all_columns": headers,
    }
