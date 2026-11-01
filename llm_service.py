import os
import json
import httpx

class LLMService:
    def __init__(self):
        self.api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        self.api_key = os.getenv("GEMINI_API_KEY")

    async def generate_response(self, user_message: str, current_profile: dict) -> dict:
        system_instruction = (
            "Ти привітний голосовий асистент AgroGrant. Твоя мета — зібрати дані для гранту. "
            "Підтримуй вільну розмову, дозволяй користувачеві розповідати своїми словами. "
            f"Поточний профіль користувача: {json.dumps(current_profile, ensure_ascii=False)}. "
            "Витягни нові дані з повідомлення користувача. Запитуй лише те, чого не вистачає. "
            "ОБОВ'ЯЗКОВО повертай відповідь у форматі JSON з двома полями: "
            "'reply' (текст для користувача) та 'extracted_data' (словник з ключами region, activity_type, "
            "size_category, employees_count, де значення - це рядок або null)."
        )

        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
            "generationConfig": {"response_mime_type": "application/json"}
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}?key={self.api_key}",
                headers=headers,
                json=payload,
                timeout=15.0
            )
            
            if response.status_code == 200:
                data = response.json()
                text_response = data['candidates'][0]['content']['parts'][0]['text']
                try:
                    return json.loads(text_response)
                except:
                    return {"reply": "Сталася помилка обробки.", "extracted_data": {}}
            return {"reply": "Вибачте, наразі сервіс генерації відповідей тимчасово недоступний.", "extracted_data": {}}