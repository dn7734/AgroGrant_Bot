"""
Модуль генерації аналітичного звіту та грантової заявки у форматі DOCX (AgroGrant_Bot).
"""

import io
from datetime import datetime
from docx import Document
from docx.shared import Pt
from grant_scraper import evaluate_grants


def create_grant_document(profile_data: dict, grants_list: list = None) -> io.BytesIO:
    """Формує файл AgroGrant_Analytical_Report.docx на основі профілю підприємства."""
    doc = Document()
    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Arial"
    normal_style.font.size = Pt(11)

    doc.add_heading("АНАЛІТИЧНИЙ ЗВІТ ОЦІНКИ ГРАНТОСПРОМОЖНОСТІ АГРАРНОГО ПІДПРИЄМСТВА", 0)
    doc.add_paragraph(
        f"Дата формування: {datetime.utcnow().strftime('%d.%m.%Y')} | "
        f"Система цифрового консалтингу: AgroGrant Analytics"
    )

    doc.add_heading("1. Реєстраційна картка та параметри учасника АПК", level=1)
    fields = [
        ("Код ЄДРПОУ та Назва", f"{profile_data.get('company_name', 'Агропідприємство')} ({profile_data.get('edrpou', 'Не вказано')})"),
        ("Основний КВЕД", profile_data.get("kved", "01.11 Вирощування зернових і технічних культур")),
        ("Регіон діяльності", profile_data.get("region", "Україна")),
        ("Спеціалізація", profile_data.get("activity_type", "Агровиробництво та переробка")),
        ("Земельний банк / Масштаб", profile_data.get("size_category", "300 га")),
        ("Штат працівників", profile_data.get("employees_count", "14 працівників")),
        ("Частка власного співфінансування", profile_data.get("own_contribution_percent", "30%")),
        ("Інвестиційний фокус проєкту", profile_data.get("investment_focus", "Модернізація та переробка"))
    ]

    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "Параметр підприємства"
    table.rows[0].cells[1].text = "Верифіковане значення"

    for label, value in fields:
        row_cells = table.add_row().cells
        row_cells[0].text = label
        row_cells[1].text = str(value)

    doc.add_heading("2. Рейтинг релевантних грантових програм (за індексом скорингу)", level=1)
    scored = evaluate_grants(profile_data, grants_list)
    for item in scored:
        p = doc.add_paragraph()
        p.add_run(f"• {item['title']} — Відповідність: {item['score']}% ({item['status']})
").bold = True
        p.add_run(f"Донор: {item['donor']} | Сума: {item['max_amount']} | Власний внесок: від {item['min_own_percent']}%
")
        p.add_run(f"Вимоги: {item['requirements']}
")
        p.add_run(f"Висновок скорингу: {item['reason']}")

    stream = io.BytesIO()
    doc.save(stream)
    stream.seek(0)
    return stream
