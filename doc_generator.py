from docx import Document
import io
import re
from datetime import datetime
from grant_scraper import evaluate_grants

def _parse_amount(text: str) -> float:
    nums = re.findall(r"\d+", str(text).replace(" ", ""))
    return float(nums[0]) if nums else 0.0

def create_grant_document(profile_data: dict, grants_list: list = None) -> io.BytesIO:
    doc = Document()
    doc.add_heading('Аналітичний звіт та грантова заявка агропідприємства', 0)
    doc.add_paragraph(f"Дата формування: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} | Система «AgroGrant»")

    doc.add_heading('1. Профіль підприємства', level=1)
    fields = [
        ("ЄДРПОУ", profile_data.get("edrpou") or "Не вказано"),
        ("Назва", profile_data.get("company_name") or "Не вказано"),
        ("КВЕД", profile_data.get("kved") or "Не вказано"),
        ("Регіон", profile_data.get("region") or "Не вказано"),
        ("Розмір/Земля", profile_data.get("size_category") or "Не вказано"),
        ("Працівники", profile_data.get("employees_count") or "Не вказано"),
        ("Власний внесок", f"{profile_data.get('own_contribution_percent') or 0}%"),
    ]
    table = doc.add_table(rows=1, cols=2)
    for label, value in fields:
        row_cells = table.add_row().cells
        row_cells[0].text = label
        row_cells[1].text = str(value)

    doc.add_heading('2. Матриця скорингу грантів', level=1)
    scored_grants = evaluate_grants(profile_data, grants_list)
    score_table = doc.add_table(rows=1, cols=4)
    sh = score_table.rows[0].cells
    sh[0].text, sh[1].text, sh[2].text, sh[3].text = 'Програма', 'Умови', 'Сумісність', 'Висновок'
    for item in scored_grants[:3]:
        rc = score_table.add_row().cells
        rc[0].text = item['title']
        rc[1].text = item['max_amount']
        rc[2].text = f"{item['score']}%"
        rc[3].text = item['reason']

    doc.add_heading('3. Фінансово-економічне обґрунтування (Прогноз)', level=1)
    if scored_grants:
        top_grant = scored_grants[0]
        grant_amt = _parse_amount(top_grant['max_amount'])
        user_own_pct = float(profile_data.get("own_contribution_percent") or top_grant['min_own_percent'])
        own_pct = max(user_own_pct, top_grant['min_own_percent'])
        
        if grant_amt > 0 and own_pct < 100:
            total_budget = grant_amt / (1 - (own_pct / 100))
            own_funds = total_budget - grant_amt
            payback_years = 3.5 if "сад" in top_grant['title'].lower() else 1.5
            roi = round((total_budget * 0.25 * payback_years) / total_budget * 100, 1)

            doc.add_paragraph(f"Пріоритетна програма: {top_grant['title']}")
            doc.add_paragraph(f"• Орієнтовний загальний бюджет проєкту: {int(total_budget):,} грн".replace(",", " "))
            doc.add_paragraph(f"• Грантові кошти ({100 - int(own_pct)}%): {int(grant_amt):,} грн".replace(",", " "))
            doc.add_paragraph(f"• Власне співфінансування ({int(own_pct)}%): {int(own_funds):,} грн".replace(",", " "))
            doc.add_paragraph(f"• Розрахунковий період окупності (Payback Period): ~{payback_years} року")
            doc.add_paragraph(f"• Очікуваний базовий ROI: {roi}%")
        else:
            doc.add_paragraph("Для детального фінансового розрахунку недостатньо числових даних гранту.")

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream