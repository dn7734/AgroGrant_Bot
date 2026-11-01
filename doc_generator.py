from docx import Document
import io
from datetime import datetime

def create_grant_document(profile_data: dict) -> io.BytesIO:
    doc = Document()
    doc.add_heading('Грантова заявка агропідприємства', 0)
    doc.add_paragraph(f"Дата формування: {datetime.utcnow().strftime('%d.%m.%Y')}")

    doc.add_heading('1. Інформаційний профіль підприємства', level=1)
    fields = [
        ("Регіон діяльності", profile_data.get("region")),
        ("Основний напрям діяльності", profile_data.get("activity_type")),
        ("Категорія підприємства за розміром", profile_data.get("size_category")),
        ("Кількість працівників", profile_data.get("employees_count")),
        ("Напрям інвестицій (ціль гранту)", profile_data.get("investment_focus")),
        ("Готовність до співфінансування (%)", profile_data.get("own_contribution_percent")),
    ]

    table = doc.add_table(rows=1, cols=2)
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Параметр оцінки'
    hdr_cells[1].text = 'Значення підприємства'

    for label, value in fields:
        row_cells = table.add_row().cells
        row_cells[0].text = label
        row_cells[1].text = str(value) if value else 'Не вказано'

    doc.add_heading('2. Рекомендовані грантові програми', level=1)
    focus = (profile_data.get("investment_focus") or "").lower()
    if "теплиц" in focus or "сад" in focus or "ягід" in focus:
        doc.add_paragraph("• Державний грант єРобота на розвиток садівництва, ягідництва та тепличного господарства (до 70% вартості проєкту).")
    elif "перероб" in focus or "обладнан" in focus:
        doc.add_paragraph("• Грант на переробне підприємство (співфінансування 50/50 або 80/20 для прифронтових регіонів).")
    else:
        doc.add_paragraph("• Мікрогрант «Власна справа» для агробізнесу та програми підтримки USAID АГРО.")

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream