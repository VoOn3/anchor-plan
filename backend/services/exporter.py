import xlsxwriter


def export_to_xlsx(plan: list[dict], analysis: list[dict], output_path: str):
    workbook = xlsxwriter.Workbook(output_path)

    header_fmt = workbook.add_format({
        "bold": True,
        "bg_color": "#1a1a2e",
        "font_color": "#ffffff",
        "border": 1,
        "text_wrap": True,
        "valign": "vcenter",
        "align": "center",
    })
    high_fmt = workbook.add_format({"bg_color": "#ff6b6b", "font_color": "#fff", "border": 1, "align": "center"})
    medium_fmt = workbook.add_format({"bg_color": "#ffd93d", "font_color": "#333", "border": 1, "align": "center"})
    low_fmt = workbook.add_format({"bg_color": "#6bcb77", "font_color": "#fff", "border": 1, "align": "center"})
    cell_fmt = workbook.add_format({"border": 1, "text_wrap": True, "valign": "vcenter"})
    center_fmt = workbook.add_format({"border": 1, "align": "center", "valign": "vcenter"})

    write_plan_sheet(workbook, plan, header_fmt, high_fmt, medium_fmt, low_fmt, cell_fmt, center_fmt)
    write_analysis_sheet(workbook, analysis, header_fmt, cell_fmt, center_fmt)

    workbook.close()


def write_plan_sheet(workbook, plan, header_fmt, high_fmt, medium_fmt, low_fmt, cell_fmt, center_fmt):
    ws = workbook.add_worksheet("Анкор-план")

    headers = [
        "Черга", "URL", "Рекомендований анкор", "Тип анкору",
        "Цільовий ключ", "Поточна позиція", "Динаміка", "Обґрунтування",
    ]
    widths = [8, 40, 30, 15, 30, 15, 12, 40]

    for i, (h, w) in enumerate(zip(headers, widths)):
        ws.set_column(i, i, w)
        ws.write(0, i, h, header_fmt)

    priority_fmts = {"high": high_fmt, "medium": medium_fmt, "low": low_fmt}

    for row_idx, item in enumerate(plan, start=1):
        ws.write(row_idx, 0, item.get("purchase_order", ""), center_fmt)
        ws.write(row_idx, 1, item["url"], cell_fmt)
        ws.write(row_idx, 2, item["recommended_anchor"], cell_fmt)
        ws.write(row_idx, 3, item["anchor_type"], center_fmt)
        ws.write(row_idx, 4, item["target_keyword"], cell_fmt)
        pos = item.get("current_position")
        ws.write(row_idx, 5, pos if pos else "—", center_fmt)
        ws.write(row_idx, 6, item.get("dynamics", ""), center_fmt)
        ws.write(row_idx, 7, item.get("rationale", item.get("comment", "")), cell_fmt)

    ws.autofilter(0, 0, len(plan), len(headers) - 1)
    ws.freeze_panes(1, 0)


def write_analysis_sheet(workbook, analysis, header_fmt, cell_fmt, center_fmt):
    ws = workbook.add_worksheet("Аналіз сторінок")

    headers = [
        "URL", "Рекомендація", "Пріоритет", "Пріоритет (бал)", "Кращий ключ",
        "Позиція", "Динаміка", "Всього бекл.", "Dofollow",
        "Унікальних анкорів", "Ключових слів",
    ]
    widths = [40, 20, 12, 15, 30, 10, 12, 12, 12, 15, 15]

    rec_labels = {
        "priority": "Пріоритетно", "recommended": "Рекомендовано",
        "needs_support": "Потребує підтримки", "has_potential": "Має потенціал",
        "observe": "Спостерігати", "not_recommended": "Не рекомендовано",
    }

    for i, (h, w) in enumerate(zip(headers, widths)):
        ws.set_column(i, i, w)
        ws.write(0, i, h, header_fmt)

    for row_idx, page in enumerate(analysis, start=1):
        bk = page.get("best_keyword")
        rec = page.get("recommendation", "not_recommended")
        ws.write(row_idx, 0, page["url"], cell_fmt)
        ws.write(row_idx, 1, rec_labels.get(rec, rec), center_fmt)
        ws.write(row_idx, 2, page["priority"].upper(), center_fmt)
        ws.write(row_idx, 3, page["priority_score"], center_fmt)
        ws.write(row_idx, 4, bk["keyword"] if bk else "—", cell_fmt)
        ws.write(row_idx, 5, bk["current_position"] if bk and bk["current_position"] else "—", center_fmt)
        ws.write(row_idx, 6, bk["dynamics_label"] if bk else "—", center_fmt)
        ws.write(row_idx, 7, page["total_backlinks"], center_fmt)
        ws.write(row_idx, 8, page["dofollow_count"], center_fmt)
        ws.write(row_idx, 9, page["anchor_profile"]["unique_anchors"], center_fmt)
        ws.write(row_idx, 10, len(page["keywords"]), center_fmt)

    ws.autofilter(0, 0, len(analysis), len(headers) - 1)
    ws.freeze_panes(1, 0)
