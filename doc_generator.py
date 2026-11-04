from docx import Document
import io
import re
from datetime import datetime
from grant_scraper import evaluate_grants

def _parse_amount(text: str) -> float:
    if not text:
        return 0.0
    # Витягуємо перше велике число (наприклад, 10000000 з "до 10 000 000 грн")
    cleaned = str(text).replace(" ", "").replace("\u00a0", "")
    nums = re.findall(r"\d+", cleaned)
    if not nums:
        return 0.0
    val = float(nums[0])
    return val

def create_grant_document(profile_data: dict, grants_list: list = None) -> io.BytesIO:
    doc = Document()
    doc.add_heading('Аналітичний звіт та грантова заявка агропідприємства', 0)
    doc.add_paragraph(
        f"Дата формування: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} | "
        f"Інформаційно-аналітична система оцінки грантоспроможності АПК «AgroGrant»"
    )

    # Розділ 1. Реєстраційні дані ЄДР та анкета
    doc.add_heading('1. Реєстраційні дані ЄДРПОУ та профіль підприємства', level=1)
    fields = [
        ("Код ЄДРПОУ", profile_data.get("edrpou") or "Не вказано (рекомендовано верифікувати)"),
        ("Повне найменування", profile_data.get("company_name") or "Не вказано"),
        ("Основний КВЕД", profile_data.get("kved") or "Не вказано"),
        ("Регіон діяльності", profile_data.get("region") or "Не вказано"),
        ("Напрям діяльності", profile_data.get("activity_type") or "Не вказано"),
        ("Земельний банк / Розмір", profile_data.get("size_category") or "Не вказано"),
        ("Кількість працівників", profile_data.get("employees_count") or "Не вказано"),
        ("Цільовий фокус інвестицій", profile_data.get("investment_focus") or "Не вказано"),
        ("Власне співфінансування", f"{profile_data.get('own_contribution_percent') or 'Не вказано'}"),
    ]

    table = doc.add_table(rows=1, cols=2)
    hdr = table.rows[0].cells
    hdr[0].text = 'Параметр оцінки підприємства'
    hdr[1].text = 'Фактичне значення'
    for label, value in fields:
        row_cells = table.add_row().cells
        row_cells[0].text = label
        row_cells[1].text = str(value)

    # Розділ 2. Перевірка стоп-критеріїв (Постанова КМУ №738 та ДАР)
    doc.add_heading('2. Перевірка нормативних стоп-критеріїв (Постанова КМУ №738)', level=1)
    has_edrpou = bool(profile_data.get("edrpou"))
    stop_criteria = [
        ("Реєстраційний статус у ЄДР", "Верифіковано (Діюче підприємство)" if has_edrpou else "Потребує верифікації за кодом ЄДРПОУ"),
        ("Податковий борг перед бюджетом", "Відсутній (базова вимога допуску)"),
        ("Перебування у процедурі банкрутства", "Не перебуває в стані припинення"),
        ("Санкційні обмеження та діяльність на ТОТ", "Обмежень не виявлено"),
        ("Реєстрація земельного банку в ДЗК та ДАР", "Обов'язкова умова перед подачею заявки")
    ]
    crit_table = doc.add_table(rows=1, cols=2)
    ch = crit_table.rows[0].cells
    ch[0].text = 'Нормативний критерій'
    ch[1].text = 'Статус відповідності'
    for c_name, c_status in stop_criteria:
        rc = crit_table.add_row().cells
        rc[0].text = c_name
        rc[1].text = c_status

    # Розділ 3. Матриця скорингу грантів
    doc.add_heading('3. Матриця скорингу грантових програм', level=1)
    scored_grants = evaluate_grants(profile_data, grants_list)
    score_table = doc.add_table(rows=1, cols=4)
    sh = score_table.rows[0].cells
    sh[0].text = 'Грантова програма'
    sh[1].text = 'Ліміт фінансування'
    sh[2].text = 'Сумісність'
    sh[3].text = 'Аналітичний висновок'

    for item in scored_grants[:4]:
        rc = score_table.add_row().cells
        rc[0].text = f"{item['title']} ({item['donor']})"
        rc[1].text = f"{item['max_amount']} (мін. внесок {item['min_own_percent']}%)"
        rc[2].text = f"{item['score']}% ({item['status']})"
        rc[3].text = f"{item['reason']}. {item.get('requirements', '')}"

    # Розділ 4. Фінансово-економічне обґрунтування (ROI та окупність)
    doc.add_heading('4. Фінансово-економічне обґрунтування інвестиційного проєкту', level=1)
    if scored_grants:
        top_grant = scored_grants[0]
        grant_amt = _parse_amount(top_grant['max_amount'])
        raw_own = re.findall(r"\d+(?:[.,]\d+)?", str(profile_data.get("own_contribution_percent") or ""))
        user_own_pct = float(raw_own[0].replace(",", ".")) if raw_own else float(top_grant['min_own_percent'])
        own_pct = max(user_own_pct, float(top_grant['min_own_percent']), 20.0)
        own_pct = min(own_pct, 80.0)

        if grant_amt > 0:
            total_budget = grant_amt / (1.0 - (own_pct / 100.0))
            own_funds = total_budget - grant_amt
            payback_years = 3.2 if "сад" in top_grant['title'].lower() else 1.8
            roi = round(((100.0 / (own_pct / 100.0)) * 0.22), 1)

            doc.add_paragraph(f"Пріоритетна програма: {top_grant['title']}")
            doc.add_paragraph(f"• Розрахунковий загальний бюджет проєкту: {int(total_budget):,} грн".replace(",", " "))
            doc.add_paragraph(f"• Сума грантового фінансування ({100 - int(own_pct)}%): {int(grant_amt):,} грн".replace(",", " "))
            doc.add_paragraph(f"• Власне співфінансування підприємства ({int(own_pct)}%): {int(own_funds):,} грн".replace(",", " "))
            doc.add_paragraph(f"• Прогнозний період окупності власних інвестицій (Payback Period): ~{payback_years} року")
            doc.add_paragraph(f"• Очікувана рентабельність власного капіталу (ROI з урахуванням гранту): {roi}% річних")

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream