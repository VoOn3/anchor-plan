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


def parse_positions_file(file_path: str) -> list[dict]:
    """
    Очікуваний формат файлу позицій:
    Колонки: URL | Keyword | дата1 | дата2 | ... | датаN
    Значення в колонках дат — позиція ключа на цю дату.
    """
    df = read_file(file_path)

    url_col = find_column(df, ["url", "page", "сторінка", "landing page", "target url", "landing"])
    keyword_col = find_column(df, ["keyword", "ключ", "ключове слово", "query", "запит", "ключевое слово"])

    if not url_col or not keyword_col:
        raise ValueError(
            "Не знайдено колонки URL або Keyword. "
            "Переконайтесь, що файл містить колонки з назвами на кшталт 'URL' та 'Keyword'."
        )

    date_columns = [c for c in df.columns if c not in [url_col, keyword_col] and is_date_like(c)]

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

        if positions:
            results.append({
                "url": url,
                "keyword": keyword,
                "positions": positions,
            })

    return results


def parse_ahrefs_file(file_path: str) -> list[dict]:
    """
    Очікуваний формат вигрузки Ahrefs (Backlinks або Anchors report):
    Колонки можуть включати: Referring Page | Anchor | Target URL | Type | DR | Traffic тощо.
    """
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


def parse_position(val) -> int | None:
    if pd.isna(val):
        return None
    try:
        num = int(float(val))
        if 1 <= num <= 1000:
            return num
    except (ValueError, TypeError):
        pass
    val_str = str(val).strip()
    if val_str in ("-", "", "n/a", "—", "–"):
        return None
    match = re.search(r"\d+", val_str)
    if match:
        num = int(match.group())
        if 1 <= num <= 1000:
            return num
    return None


def safe_float(val) -> float | None:
    if pd.isna(val):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
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
