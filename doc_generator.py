from docx import Document
import io

def create_grant_document(profile_data: dict) -> io.BytesIO:
    doc = Document()
    doc.add_heading('Грантова заявка агропідприємства', 0)

    doc.add_heading('Основні відомості', level=1)
    doc.add_paragraph(f"Регіон: {profile_data.get('region', 'Не вказано')}")
    doc.add_paragraph(f"Сфера діяльності: {profile_data.get('activity_type', 'Не вказано')}")
    doc.add_paragraph(f"Категорія розміру: {profile_data.get('size_category', 'Не вказано')}")
    doc.add_paragraph(f"Кількість працівників: {profile_data.get('employees_count', 'Не вказано')}")

    doc.add_heading('Фінансовий фокус', level=1)
    doc.add_paragraph(f"Фокус інвестицій: {profile_data.get('investment_focus', 'Не вказано')}")
    doc.add_paragraph(f"Власний внесок (%): {profile_data.get('own_contribution_percent', 'Не вказано')}")

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream