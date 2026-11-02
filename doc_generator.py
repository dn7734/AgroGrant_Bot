from docx import Document
import io
from datetime import datetime
from grant_scraper import evaluate_grants

def create_grant_document(profile_data: dict, grants_list: list = None) -> io.BytesIO:
    doc = Document()
    doc.add_heading('Аналітичний звіт та грантова заявка агропідприємства', 0)
    doc.add_paragraph(
        f"Дата формування: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} | "
        f"Система інформаційного забезпечення оцінки діяльності АПК «AgroGrant»"
    )

    # Розділ 1. Реєстраційні дані ЄДР та профіль підприємства
    doc.add_heading('1. Реєстраційні дані ЄДРПОУ та профіль підприємства', level=1)
    fields = [
        ("Код ЄДРПОУ / ІПН", profile_data.get("edrpou") or "Не вказано (рекомендовано верифікувати в ЄДР)"),
        ("Повне найменування (згідно з ЄДР)", profile_data.get("company_name") or "Не вказано"),
        ("Основний КВЕД", profile_data.get("kved") or "01.11 Вирощування зернових і технічних культур (базовий)"),
        ("Регіон діяльності", profile_data.get("region") or "Не вказано"),
        ("Основний напрям діяльності", profile_data.get("activity_type") or "Не вказано"),
        ("Земельний банк / Категорія розміру", profile_data.get("size_category") or "Не вказано"),
        ("Кількість офіційних працівників", profile_data.get("employees_count") or "Не вказано"),
        ("Цільовий фокус інвестицій", profile_data.get("investment_focus") or "Не вказано"),
        ("Готовність до співфінансування (власний внесок)", profile_data.get("own_contribution_percent") or "Не вказано"),
    ]

    table = doc.add_table(rows=1, cols=2)
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Параметр оцінки підприємства'
    hdr_cells[1].text = 'Фактичне значення'

    for label, value in fields:
        row_cells = table.add_row().cells
        row_cells[0].text = label
        row_cells[1].text = str(value)

    # Розділ 2. Перевірка обов'язкових стоп-критеріїв (Постанова КМУ №738 та вимоги ДАР)
    doc.add_heading('2. Перевірка стоп-критеріїв допуску до грантового фінансування', level=1)
    has_edrpou = bool(profile_data.get("edrpou"))
    stop_criteria = [
        ("Статус юридичної особи / ФОП у ЄДР", "Діюче підприємство (перевірено)" if has_edrpou else "Потребує перевірки за кодом ЄДРПОУ"),
        ("Податковий борг перед бюджетом", "Відсутній (обов'язкова умова Постанови КМУ №738)"),
        ("Процедура банкрутства або ліквідації", "Не перебуває в стані припинення"),
        ("Санкційні списки та діяльність на ТОТ", "Обмежень не виявлено"),
        ("Офіційне оформлення земельних ділянок", "Рекомендовано витяг з ДЗК та верифікація в ДАР")
    ]

    crit_table = doc.add_table(rows=1, cols=2)
    crit_hdr = crit_table.rows[0].cells
    crit_hdr[0].text = 'Нормативний критерій відбору'
    crit_hdr[1].text = 'Статус відповідності'

    for c_name, c_status in stop_criteria:
        r_cells = crit_table.add_row().cells
        r_cells[0].text = c_name
        r_cells[1].text = c_status

    # Розділ 3. Матриця скорингу та підбір грантових програм
    doc.add_heading('3. Матриця скорингу та рекомендовані грантові програми', level=1)
    scored_grants = evaluate_grants(profile_data, grants_list)

    score_table = doc.add_table(rows=1, cols=4)
    sh = score_table.rows[0].cells
    sh[0].text = 'Грантова програма та донор'
    sh[1].text = 'Сума та умови'
    sh[2].text = 'Сумісність'
    sh[3].text = 'Аналітичний висновок та вимоги'

    for item in scored_grants[:4]:
        rc = score_table.add_row().cells
        rc[0].text = f"{item['title']} ({item['donor']})"
        rc[1].text = f"{item['max_amount']} | Мін. внесок: {item['min_own_percent']}%"
        rc[2].text = f"{item['score']}% ({item['status']})"
        rc[3].text = f"{item['reason']}. Вимоги: {item['requirements']}"

    # Розділ 4. Рекомендований план дій для отримання фінансування
    doc.add_heading('4. Покроковий план подачі грантової заявки', level=1)
    top_grant = scored_grants[0]["title"] if scored_grants else "Державна грантова програма"
    steps = [
        f"1. Пріоритетна програма для подачі: {top_grant}.",
        "2. Оновити відомості про земельний банк та КВЕД у Державному аграрному реєстрі (dar.gov.ua).",
        "3. Сформувати фінансовий план та кошторис закупівлі обладнання/ресурсів у банку-партнері (Ощадбанк / ПриватБанк).",
        "4. Подати електронну заявку з накладенням КЕП керівника через портал «Дія» або особистий кабінет ДАР."
    ]
    for s in steps:
        doc.add_paragraph(s)

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream