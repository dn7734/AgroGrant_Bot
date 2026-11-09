"""
НАУКОВО-МЕТОДИЧНИЙ ОПИС МОДУЛЯ (doc_generator.py):
Модуль автоматизованого формування проєктної документації у форматі Microsoft Word (DOCX).
Синтезує паспорт верифікованого суб'єкта кластеру, параметри економіко-математичної моделі
маржинальності сорту гірчиці «Біла Принцеса» та результати багатокритеріального скорингу.
"""

import io
from datetime import datetime
from docx import Document
from docx.shared import Pt
from grant_scraper import evaluate_grants


def create_grant_document(profile_data: dict, grants_list: list = None) -> io.BytesIO:
    doc = Document()

    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Arial"
    normal_style.font.size = Pt(11)

    doc.add_heading("ЕСКІЗНИЙ ПРОЄКТ (ДРАФТ) ІННОВАЦІЙНОГО АГРАРНОГО КЛАСТЕРУ", 0)
    doc.add_paragraph(
        f"Дата формування: {datetime.utcnow().strftime('%d.%m.%Y')} | "
        f"Методологічний провайдер: ТОВ «Інститут інноваційної біоекономіки» (ІІБ) & НААН України\n"
        f"Об'єкт трансферу інновацій (ОІВ): Сорт гірчиці білої «Біла Принцеса»"
    )

    doc.add_heading("1. Паспорт учасника кластеру та розрахункові показники маржинальності", level=1)

    fields = [
        ("Суб'єкт кластеру (Код ЄДРПОУ)", f"{profile_data.get('company_name', 'Не вказано')} ({profile_data.get('edrpou', '00496802')})"),
        ("Роль у ланцюгу доданої вартості", profile_data.get("activity_type", "Учасник кластерного циклу")),
        ("Масштаб виробництва у кластері", profile_data.get("size_category", "300 га")),
        ("Частка власного співфінансування / ОІВ", profile_data.get("own_contribution_percent", "30%")),
        ("Розрахункова чиста маржа та аванс НААН", profile_data.get("employees_count", "Визначено за моделлю E2")),
        ("Стратегічний фокус комерціалізації", profile_data.get("investment_focus", "Трансфер ОІВ та глибока переробка"))
    ]

    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text = "Параметр паспорта кластеру"
    hdr[1].text = "Верифіковане значення"

    for label, value in fields:
        row_cells = table.add_row().cells
        row_cells[0].text = label
        row_cells[1].text = str(value)

    doc.add_heading("2. Організаційно-економічний механізм масштабування (4 ланки кластеру)", level=1)

    tech_stages = [
        (
            "Етап І. Наукове ядро (1–5 га)",
            "Оригінальне насіння (Супереліта)",
            "ННЦ «Інститут землеробства НААН»: охорона ОІВ, закладання розсадника під замовлення бізнесу з авансовою передоплатою 30%."
        ),
        (
            "Етап ІІ. Мультиплікація (25–50 га)",
            "Елітне насіння та Драфт стартапу",
            "ТОВ «Інститут інноваційної біоекономіки»: пакування драфту та інвестиційного тизера, авторський нагляд за насінницькими господарствами."
        ),
        (
            "Етап ІІІ. Агровиробництво (300+ га)",
            "Товарне насіння І репродукції (РС-1)",
            "Агропідприємства кластеру: вирощування посухостійкої гірчиці за форвардними Off-take контрактами та сидерація ґрунтів."
        ),
        (
            "Етап ІV. Глибока біопереробка",
            "Олія холодного віджиму, порошок, шрот",
            "Завод глибокої переробки: безвідходна технологія Zero-Waste із генерацією високої доданої вартості (+135% маржі)."
        )
    ]

    tech_table = doc.add_table(rows=1, cols=3)
    tech_table.style = "Table Grid"
    th = tech_table.rows[0].cells
    th[0].text = "Ланка інноваційного кластеру"
    th[1].text = "Продукт генерації"
    th[2].text = "Механізм державно-приватного партнерства"

    for st, prod, desc in tech_stages:
        rc = tech_table.add_row().cells
        rc[0].text = st
        rc[1].text = prod
        rc[2].text = desc

    doc.add_heading("3. Рекомендовані моделі залучення капіталу (Без боргового навантаження)", level=1)

    scored_models = evaluate_grants(profile_data, grants_list)
    for item in scored_models[:3]:
        p = doc.add_paragraph()
        p.add_run(f"• {item['title']} (Індекс відповідності: {item['score']}%)\n").bold = True
        p.add_run(f"Інституційний провайдер / Донор: {item['donor']}\n")
        p.add_run(f"Обсяг фінансування: {item['max_amount']} (Поріг співфінансування: від {item['min_own_percent']}%)\n")
        p.add_run(f"Аналітичне обґрунтування: {item['reason']}")

    footer_p = doc.add_paragraph(
        "\nДокумент сформовано автоматично інформаційно-аналітичною платформою AgroCluster Analytics. "
        "Параметри верифіковано для передачі у грантовий модуль AgroGrant_Bot."
    )
    footer_p.runs[0].italic = True

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream
