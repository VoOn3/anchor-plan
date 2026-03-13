import pandas as pd
import re
from urllib.parse import urlparse


def normalize_url(url: str) -> str:
    if not url or not isinstance(url, str):
        return ""
    url = url.strip().lower()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def url_to_canonical(url: str) -> str:
    """
    Канонічний URL для групування сторінок: https, без www, path без trailing slash.
    Використовується для об'єднання www/non-www та http/https варіантів однієї сторінки.
    """
    if not url or not isinstance(url, str):
        return ""
    url = url.strip().lower()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/") or "/"
    return f"https://{host}{path}"


def parse_positions_file(file_path: str) -> list[dict]:
    """
    Підтримує формати:
    - Pivot: URL | Keyword | дата1 | дата2 | ... | датаN
    - SE Ranking (long): Keyword | URL | SERP Date | Rank
    """
    df = read_positions_file(file_path)

    # Спроба формату SE Ranking (long: один рядок на keyword-URL-дату)
    if _is_seranking_format(df):
        return _parse_seranking_positions(df)

    # Стандартний pivot-формат
    url_col = find_column(df, ["url", "page", "сторінка", "landing page", "target url", "landing"])
    keyword_col = find_column(df, ["keyword", "ключ", "ключове слово", "query", "запит", "ключевое слово"])
    volume_col = find_column(df, [
        "volume", "search volume", "search_volume", "sv", "traffic", "частота", "частотность", "запитів",
        "monthly searches", "monthly_searches"
    ])

    if not url_col or not keyword_col:
        raise ValueError(
            "Не знайдено колонки URL або Keyword. "
            "Переконайтесь, що файл містить колонки з назвами на кшталт 'URL' та 'Keyword'."
        )

    date_columns = [c for c in df.columns if c not in [url_col, keyword_col, volume_col] and is_date_like(c)]

    if not date_columns:
        raise ValueError("Не знайдено колонок з датами позицій.")

    results = []
    for _, row in df.iterrows():
        url = normalize_url(str(row[url_col]))
        keyword = str(row[keyword_col]).strip()
        if not url or not keyword:
            continue

        positions = {}
        for dc in date_columns:
            val = row[dc]
            pos = parse_position(val)
            if pos is not None:
                positions[str(dc)] = pos

        volume = None
        if volume_col and pd.notna(row.get(volume_col)):
            volume = parse_volume(row[volume_col])

        if positions:
            item = {"url": url, "keyword": keyword, "positions": positions}
            if volume is not None:
                item["volume"] = volume
            results.append(item)

    return results


def _is_seranking_format(df: pd.DataFrame) -> bool:
    """SE Ranking: long-формат — Keyword, URL, SERP Date, Rank (один рядок на дату)."""
    date_like_cols = [c for c in df.columns if is_date_like(c)]
    if len(date_like_cols) > 2:
        return False  # Pivot: багато колонок-дат
    kw_col = find_column(df, ["keyword", "ключ", "ключове слово", "query", "ключевое слово"])
    url_col = find_column(df, ["url", "page", "landing page", "target url", "landing", "сторінка"])
    date_col = find_column(df, ["serp date", "date", "дата", "updated on", "serp_date"])
    rank_col = find_column(df, ["rank", "position", "позиція", "position change"])
    return bool(kw_col and url_col and date_col and rank_col)


def _parse_seranking_positions(df: pd.DataFrame) -> list[dict]:
    """Парсить long-формат SE Ranking: групує по (url, keyword), збирає positions з date+rank."""
    kw_col = find_column(df, ["keyword", "ключ", "ключове слово", "query", "ключевое слово"])
    url_col = find_column(df, ["url", "page", "landing page", "target url", "landing", "сторінка"])
    date_col = find_column(df, ["serp date", "date", "дата", "updated on", "serp_date"])
    rank_col = find_column(df, ["rank", "position", "позиція", "position change"])
    volume_col = find_column(df, [
        "volume", "search volume", "search_volume", "sv", "traffic", "частота", "частотность",
        "monthly searches", "monthly_searches"
    ])

    grouped: dict[tuple[str, str], dict] = {}
    for _, row in df.iterrows():
        url = normalize_url(str(row[url_col]))
        keyword = str(row[kw_col]).strip()
        if not url or not keyword:
            continue
        date_val = row.get(date_col)
        if pd.isna(date_val):
            continue
        date_str = _normalize_date_column(date_val)
        if not date_str:
            continue
        pos = parse_position(row.get(rank_col))
        key = (url, keyword)
        if key not in grouped:
            vol = None
            if volume_col and pd.notna(row.get(volume_col)):
                vol = parse_volume(row.get(volume_col))
            grouped[key] = {"url": url, "keyword": keyword, "positions": {}, "volume": vol}
        grouped[key]["positions"][date_str] = pos
        if grouped[key]["volume"] is None and volume_col and pd.notna(row.get(volume_col)):
            grouped[key]["volume"] = parse_volume(row.get(volume_col))

    results = []
    for g in grouped.values():
        if g["positions"]:
            item = {"url": g["url"], "keyword": g["keyword"], "positions": g["positions"]}
            if g["volume"] is not None:
                item["volume"] = g["volume"]
            results.append(item)
    return results


def _normalize_date_column(val) -> str | None:
    """Повертає YYYY-MM-DD для колонки дати."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        try:
            dt = pd.to_datetime(s[:10])
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass
    try:
        dt = pd.to_datetime(val, dayfirst=True)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def parse_ahrefs_file(file_path: str) -> list[dict]:
    """
    Автоматично визначає формат файлу:
    - Collaborator export (XLSX з листами "Розподіл по операціях" тощо)
    - Ahrefs backlinks/anchors report
    """
    if _is_collaborator_export(file_path):
        return _parse_collaborator_export(file_path)

    return _parse_ahrefs_standard(file_path)


def parse_ahrefs_backlinks(file_path: str) -> list[dict]:
    """Парсить тільки формат Ahrefs, додає source: 'ahrefs'."""
    data = _parse_ahrefs_standard(file_path)
    for item in data:
        item["source"] = "ahrefs"
    return data


def parse_collaborator_backlinks(file_path: str) -> list[dict]:
    """Парсить тільки формат Collaborator (XLSX з Розподіл по операціях), додає source: 'collaborator'."""
    data = _parse_collaborator_export(file_path)
    for item in data:
        item["source"] = "collaborator"
    return data


def parse_backlinks_auto(file_path: str) -> list[dict]:
    """Автовизначення формату (зворотна сумісність для старих проектів)."""
    if _is_collaborator_export(file_path):
        return parse_collaborator_backlinks(file_path)
    return parse_ahrefs_backlinks(file_path)


def _is_collaborator_export(file_path: str) -> bool:
    if not file_path.endswith((".xlsx", ".xls")):
        return False
    try:
        xls = pd.ExcelFile(file_path)
        for sheet in xls.sheet_names:
            lower = sheet.strip().lower()
            if "розподіл по операціях" in lower or "розподіл" in lower:
                return True
        df = pd.read_excel(file_path, sheet_name=0)
        cols_lower = {c.strip().lower() for c in df.columns}
        if "анкори" in cols_lower and "цільова сторінка" in cols_lower:
            return True
    except Exception:
        pass
    return False


def _parse_collaborator_export(file_path: str) -> list[dict]:
    xls = pd.ExcelFile(file_path)

    ops_df = _read_sheet_by_hint(xls, ["розподіл по операціях", "розподіл"])
    if ops_df is None:
        ops_df = pd.read_excel(file_path, sheet_name=0)

    guests_df = _read_sheet_by_hint(xls, ["гостьові публікації", "гостьові"])
    seo_df = _read_sheet_by_hint(xls, ["за seo метриками", "seo метрик"])

    anchor_col = find_column(ops_df, ["анкори", "анкор", "anchor"])
    target_col = find_column(ops_df, ["цільова сторінка", "цільовий url", "target url"])
    ref_col = find_column(ops_df, [
        "адреса розміщеної публікації", "адреса публікації",
        "referring page", "url публікації"
    ])
    domain_col = find_column(ops_df, ["домен", "domain"])
    deal_col = find_column(ops_df, ["угоди", "id угоди", "угода"])

    if not anchor_col or not target_col:
        raise ValueError(
            "Файл Collaborator: не знайдено колонки 'Анкори' або 'Цільова сторінка'"
        )

    seo_map = {}
    if seo_df is not None:
        seo_domain_col = find_column(seo_df, ["домен", "domain"])
        seo_deal_col = find_column(seo_df, ["id угоди", "угоди", "угода"])
        seo_dr_col = find_column(seo_df, ["dr", "domain rating"])
        seo_traffic_col = find_column(seo_df, ["органічний трафік", "organic traffic", "трафік"])

        for _, srow in seo_df.iterrows():
            key = None
            if seo_deal_col and pd.notna(srow.get(seo_deal_col)):
                key = str(int(srow[seo_deal_col])) if isinstance(srow[seo_deal_col], (int, float)) else str(srow[seo_deal_col]).strip()
            elif seo_domain_col and pd.notna(srow.get(seo_domain_col)):
                key = str(srow[seo_domain_col]).strip().lower()

            if key:
                seo_map[key] = {
                    "dr": safe_float(srow.get(seo_dr_col)) if seo_dr_col else None,
                    "traffic": safe_float(srow.get(seo_traffic_col)) if seo_traffic_col else None,
                }

    guests_map = {}
    if guests_df is not None:
        g_ref_col = find_column(guests_df, [
            "адреса розміщеної публікації", "адреса публікації", "url публікації"
        ])
        g_date_col = find_column(guests_df, ["дата розміщення", "дата"])
        g_cost_col = find_column(guests_df, ["разом, uah", "разом", "вартість розміщення, uah"])

        if g_ref_col:
            for _, grow in guests_df.iterrows():
                g_url = str(grow.get(g_ref_col, "")).strip()
                if not g_url or g_url == "nan":
                    continue
                guests_map[g_url] = {
                    "placement_date": str(grow.get(g_date_col, "")).strip() if g_date_col and pd.notna(grow.get(g_date_col)) else None,
                    "cost": _parse_cost(grow.get(g_cost_col)) if g_cost_col else None,
                }

    results = []
    for _, row in ops_df.iterrows():
        anchor = str(row.get(anchor_col, "")).strip() if pd.notna(row.get(anchor_col)) else ""
        target_url = normalize_url(str(row.get(target_col, ""))) if pd.notna(row.get(target_col)) else ""
        ref_url = str(row.get(ref_col, "")).strip() if ref_col and pd.notna(row.get(ref_col)) else ""
        domain_val = str(row.get(domain_col, "")).strip() if domain_col and pd.notna(row.get(domain_col)) else ""

        if not anchor or anchor == "nan":
            continue

        deal_id = None
        if deal_col and pd.notna(row.get(deal_col)):
            deal_id = str(int(row[deal_col])) if isinstance(row[deal_col], (int, float)) else str(row[deal_col]).strip()

        seo_data = {}
        if deal_id and deal_id in seo_map:
            seo_data = seo_map[deal_id]
        elif domain_val and domain_val.lower() in seo_map:
            seo_data = seo_map[domain_val.lower()]

        guest_data = guests_map.get(ref_url, {})

        results.append({
            "target_url": target_url,
            "anchor": anchor,
            "referring_url": ref_url,
            "link_type": "dofollow",
            "dr": seo_data.get("dr"),
            "traffic": seo_data.get("traffic"),
            "placement_date": guest_data.get("placement_date"),
            "cost": guest_data.get("cost"),
        })

    return results


def _read_sheet_by_hint(xls: pd.ExcelFile, hints: list[str]) -> pd.DataFrame | None:
    for sheet in xls.sheet_names:
        lower = sheet.strip().lower()
        for hint in hints:
            if hint in lower:
                return pd.read_excel(xls, sheet_name=sheet)
    return None


def _parse_cost(val) -> float | None:
    if pd.isna(val):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace("\xa0", "").replace(",", ".").replace(" ", "")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _parse_ahrefs_standard(file_path: str) -> list[dict]:
    df = read_file(file_path)

    target_col = find_column(df, [
        "target url", "target", "url to", "target page",
        "цільовий url", "сторінка"
    ])
    anchor_col = find_column(df, [
        "anchor", "anchor text", "анкор", "текст посилання",
        "anchor and target url"
    ])
    ref_col = find_column(df, [
        "referring page", "source url", "referring url",
        "source page", "from url", "ref page", "referring page url"
    ])
    type_col = find_column(df, ["type", "link type", "тип", "nofollow", "dofollow"])
    dr_col = find_column(df, ["dr", "domain rating", "рейтинг домену"])
    traffic_col = find_column(df, [
        "traffic", "organic traffic", "трафік", "ref page traffic",
        "page traffic"
    ])

    if not anchor_col:
        raise ValueError("Не знайдено колонки Anchor / Анкор.")

    results = []
    for _, row in df.iterrows():
        target_url = normalize_url(str(row[target_col])) if target_col else ""
        anchor = str(row[anchor_col]).strip() if pd.notna(row[anchor_col]) else ""
        ref_url = str(row[ref_col]).strip() if ref_col and pd.notna(row[ref_col]) else ""
        link_type = str(row[type_col]).strip().lower() if type_col and pd.notna(row[type_col]) else "dofollow"
        dr = safe_float(row[dr_col]) if dr_col else None
        traffic = safe_float(row[traffic_col]) if traffic_col else None

        if not anchor:
            continue

        results.append({
            "target_url": target_url,
            "anchor": anchor,
            "referring_url": ref_url,
            "link_type": link_type,
            "dr": dr,
            "traffic": traffic,
        })

    return results


def parse_anchor_plan_file(file_path: str) -> list[dict]:
    """
    Парсить файл анкор-плану. Обов'язкові колонки: URL та анкор.
    Повертає список {url, anchor}.
    """
    df = read_file(file_path)

    url_col = find_column(df, ["url", "page", "сторінка", "landing page", "target url", "landing", "цільова сторінка"])
    anchor_col = find_column(df, ["anchor", "анкор", "анкори", "keyword", "ключ", "ключове слово", "anchor text"])

    if not url_col or not anchor_col:
        raise ValueError(
            "Не знайдено колонки URL або Анкор. "
            "Переконайтесь, що файл містить колонки 'URL' та 'Анкор' (або 'Anchor')."
        )

    results = []
    for _, row in df.iterrows():
        url = normalize_url(str(row[url_col]))
        anchor = str(row[anchor_col]).strip()
        if not url or not anchor or anchor.lower() == "nan":
            continue
        results.append({"url": url, "anchor": anchor})

    if not results:
        raise ValueError("Файл не містить жодного рядка з URL та анкором.")

    return results


def read_file(file_path: str) -> pd.DataFrame:
    if file_path.endswith((".xlsx", ".xls")):
        return pd.read_excel(file_path)
    elif file_path.endswith(".csv"):
        for encoding in ["utf-8", "utf-8-sig", "cp1251", "latin-1"]:
            for sep in [",", ";", "\t"]:
                try:
                    df = pd.read_csv(file_path, encoding=encoding, sep=sep)
                    if len(df.columns) > 1:
                        return df
                except Exception:
                    continue
        return pd.read_csv(file_path)
    else:
        raise ValueError(f"Непідтримуваний формат файлу: {file_path}")


def read_positions_file(file_path: str) -> pd.DataFrame:
    """Читає CSV позицій, пропускаючи рядок метаданих якщо є (напр. Avrora, Seranking)."""
    if not file_path.endswith(".csv"):
        return read_file(file_path)
    for encoding in ["utf-8", "utf-8-sig", "cp1251", "latin-1"]:
        for sep in [",", ";", "\t"]:
            try:
                df0 = pd.read_csv(file_path, encoding=encoding, sep=sep, header=0)
                first_val = str(df0.columns[0]) if len(df0.columns) else ""
                first_cell = str(df0.iloc[0, 0]) if len(df0) and len(df0.columns) else ""
                # Пропустити рядок метаданих (напр. "Google Mobile Украина...")
                skip = (
                    len(df0.columns) == 1
                    or "google" in first_val.lower()
                    or "google" in first_cell.lower()
                    or "українська" in first_val.lower()
                    or "українська" in first_cell.lower()
                )
                if skip or len(df0.columns) < 2:
                    df = pd.read_csv(file_path, encoding=encoding, sep=sep, header=1)
                    if len(df.columns) > 1:
                        return df
                elif len(df0.columns) >= 2:
                    return df0
            except Exception:
                continue
    return read_file(file_path)


def find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    columns_lower = {c.strip().lower(): c for c in df.columns}
    for candidate in candidates:
        if candidate.lower() in columns_lower:
            return columns_lower[candidate.lower()]
    for candidate in candidates:
        for col_lower, col_orig in columns_lower.items():
            if candidate.lower() in col_lower:
                return col_orig
    return None


def is_date_like(col_name) -> bool:
    col_str = str(col_name).strip()
    date_patterns = [
        r"\d{4}-\d{2}-\d{2}",
        r"\d{2}\.\d{2}\.\d{4}",
        r"\d{2}/\d{2}/\d{4}",
        r"\d{2}-\d{2}-\d{4}",
    ]
    for pattern in date_patterns:
        if re.match(pattern, col_str):
            return True
    try:
        pd.to_datetime(col_str, dayfirst=True)
        return True
    except (ValueError, TypeError):
        pass
    return False


NO_POSITION_PLACEHOLDER = 101  # Позиція 100+ при відсутності даних


def parse_position(val) -> int:
    if pd.isna(val):
        return NO_POSITION_PLACEHOLDER
    val_str = str(val).strip()
    no_data_values = ("-", "", "n/a", "—", "–", "нет данных", "немає даних")
    if val_str.lower() in (v.lower() for v in no_data_values):
        return NO_POSITION_PLACEHOLDER
    try:
        num = int(float(val))
        if 1 <= num <= 1000:
            return num
    except (ValueError, TypeError):
        pass
    match = re.search(r"\d+", val_str)
    if match:
        num = int(match.group())
        if 1 <= num <= 1000:
            return num
    return NO_POSITION_PLACEHOLDER


def safe_float(val) -> float | None:
    if pd.isna(val):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def parse_volume(val) -> int | None:
    """Парсить частоту запитів (search volume). Повертає int або None."""
    if pd.isna(val):
        return None
    try:
        num = int(float(val))
        if num >= 0:
            return num
    except (ValueError, TypeError):
        pass
    val_str = str(val).strip().replace("\xa0", "").replace(",", "").replace(" ", "")
    match = re.search(r"\d+", val_str)
    if match:
        num = int(match.group())
        if num >= 0:
            return num
    return None


def parse_collaborator_file(file_path: str) -> list[dict]:
    import csv

    rows = []
    header = None
    for encoding in ["utf-8-sig", "utf-8", "cp1251", "latin-1"]:
        try:
            with open(file_path, encoding=encoding, newline="") as f:
                reader = csv.reader(f, delimiter=";", quotechar='"')
                header = [c.strip() for c in next(reader)]
                for row in reader:
                    rows.append(row)
            break
        except Exception:
            header = None
            rows = []
            continue

    if not header:
        raise ValueError("Не вдалось прочитати файл Collaborator")

    num_cols = len(header)
    results = []
    for row in rows:
        vals = row[:num_cols]
        if len(vals) < num_cols:
            vals += [None] * (num_cols - len(vals))

        site = {}
        for i, col in enumerate(header):
            raw = vals[i]
            if raw is None or raw.strip() == "":
                site[col] = None
            else:
                s = raw.strip()
                try:
                    site[col] = float(s.replace(",", "."))
                except (ValueError, TypeError):
                    site[col] = s

        if site.get("Домен"):
            results.append(site)

    return results


def get_collaborator_columns(sites: list[dict]) -> list[dict]:
    """Classify columns as numeric or text for filter UI."""
    if not sites:
        return []

    numeric_hints = {
        "DR", "UR", "TF", "CF", "TR", "Da Moz", "Serpstat SDR",
        "ранк Ahrefs", "Трафік на місяць", "Органічний трафік",
        "Трафік,% Дірект", "Трафік,% Реф.", "Трафік,% Орган.", "Трафік,% Соц.",
        "Кліки GSC", "Покази GSC", "Вік сайту, років",
        "Індекс Google", "Ключові слова", "Запити в топі",
        "Беклінки", "Домени-донори", "Вихідні домени",
        "Кількість посилань стаття",
        "Ціна розміщення стаття, UAH", "Ціна написання стаття, UAH",
        "Доданий до системи, років", "Google AIO",
        "IP-адреси, що посилаються", "Вхідні посилання",
        "Домени, що посилаються",
    }

    text_hints = {
        "Домен", "Тематика", "Мови сайту", "Джерело трафіку",
        "Країна", "Регіони", "Швидкість розміщення", "Біржа посилань",
        "Доменна зона", "Тип сайту", "Особливі тематики",
        "Тип посилання стаття", "Позначка про рекламу стаття",
        "URL Коллаборатора", "Ціна анонса стаття, UAH",
        "Ціна особливої \u200b\u200bтематики, UAH",
    }

    sample = sites[0]
    columns = []
    for col in sample.keys():
        if col in ("URL Коллаборатора",):
            continue
        if col in text_hints:
            col_type = "text"
        elif col in numeric_hints:
            col_type = "number"
        else:
            col_type = "text"
            for s in sites[:20]:
                v = s.get(col)
                if v is not None and isinstance(v, (int, float)):
                    col_type = "number"
                    break
        columns.append({"name": col, "type": col_type})

    return columns
