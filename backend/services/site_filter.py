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

    raw = site.get(field)
    if raw is None:
        return False

    if op in (">=", "<="):
        num = _to_float(raw)
        target_num = _to_float(target)
        if num is None or target_num is None:
            return False
        if op == ">=" and num < target_num:
            return False
        if op == "<=" and num > target_num:
            return False

    elif op == "=":
        num = _to_float(raw)
        target_num = _to_float(target)
        if num is not None and target_num is not None:
            if num != target_num:
                return False
        else:
            if str(raw).strip().lower() != str(target).strip().lower():
                return False

    elif op == "contains":
        if str(target).lower() not in str(raw).lower():
            return False

    elif op == "not_contains":
        if str(target).lower() in str(raw).lower():
            return False

    return True


def _to_float(val) -> float | None:
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None
