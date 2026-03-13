def filter_sites(sites: list[dict], filters: list[dict]) -> list[dict]:
    """
    Apply filters to collaborator sites.
    Each filter: {"field": "DR", "op": ">=", "value": 20}
    Operators: >=, <=, =, contains, not_contains
    """
    if not filters:
        return sites

    result = []
    for site in sites:
        if _matches_all(site, filters):
            result.append(site)
    return result


def _matches_all(site: dict, filters: list[dict]) -> bool:
    for f in filters:
        if not _matches(site, f):
            return False
    return True


def _matches(site: dict, f: dict) -> bool:
    field = f.get("field", "")
    op = f.get("op", "")
    target = f.get("value")

    if target is None or target == "":
        return True
    targets = [target] if not isinstance(target, list) else [t for t in target if t is not None and t != ""]
    if not targets:
        return True

    raw = site.get(field)
    if raw is None:
        return False

    raw_parts = [p.strip() for p in str(raw).split(",") if p.strip()] if raw is not None else []
    if not raw_parts:
        raw_parts = [raw]

    if op in (">=", "<="):
        num = _to_float(raw)
        if num is None:
            return False
        for t in targets:
            target_num = _to_float(t)
            if target_num is not None:
                if op == ">=" and num >= target_num:
                    return True
                if op == "<=" and num <= target_num:
                    return True
        return False

    elif op == "=":
        raw_num = _to_float(raw)
        for t in targets:
            t_num = _to_float(t)
            if raw_num is not None and t_num is not None:
                if raw_num == t_num:
                    return True
            else:
                for rp in raw_parts:
                    if str(rp).strip().lower() == str(t).strip().lower():
                        return True
        return False

    elif op == "contains":
        raw_lower = str(raw).lower()
        for t in targets:
            if str(t).lower() in raw_lower:
                return True
        return False

    elif op == "not_contains":
        raw_lower = str(raw).lower()
        for t in targets:
            if str(t).lower() in raw_lower:
                return False
        return True

    return True


def _to_float(val) -> float | None:
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None
