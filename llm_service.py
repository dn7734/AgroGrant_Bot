import os
import json
import httpx

class LLMService:
    def __init__(self):
        self.api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        self.api_key = os.getenv("GEMINI_API_KEY")

    async def generate_response(self, user_message: str, current_profile: dict) -> dict:
        if not self.api_key:
            print("ERROR: GEMINI_API_KEY is not set in environment variables!")
            return {"reply": "Помилка конфігурації: не задано GEMINI_API_KEY на сервісі Render.", "extracted_data": {}}

        system_instruction = (
            "Ти привітний голосовий асистент AgroGrant. Твоя мета — зібрати дані для гранту. "
            "Підтримуй вільну розмову, дозволяй користувачеві розповідати своїми словами. "
            f"Поточний профіль користувача: {json.dumps(current_profile, ensure_ascii=False)}. "
            "Витягни нові дані з повідомлення користувача. Запитуй лише те, чого не вистачає. "
            "ОБОВ'ЯЗКОВО повертай відповідь у форматі JSON з двома полями: "
            "'reply' (текст для користувача) та 'extracted_data' (словник з ключами region, activity_type, "
            "size_category, employees_count, investment_focus, own_contribution_percent, де значення - це рядок або null)."
        )

        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
            "generationConfig": {"response_mime_type": "application/json"}
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}?key={self.api_key}",
                    headers=headers,
                    json=payload,
                    timeout=20.0
                )
                
                print(f"Gemini API Status Code: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    text_response = data['candidates'][0]['content']['parts'][0]['text']
                    try:
                        return json.loads(text_response)
                    except Exception as e:
                        print(f"JSON decode error from Gemini response: {e}, text was: {text_response}")
                        return {"reply": "Сталася помилка обробки відповіді LLM.", "extracted_data": {}}
                else:
                    print(f"Gemini API Error Response: {response.text}")
                    return {"reply": f"Помилка від Gemini API (код {response.status_code}).", "extracted_data": {}}
        except Exception as e:
            print(f"Exception during Gemini API request: {e}")
            return {"reply": f"Помилка з'єднання з Gemini API: {str(e)}", "extracted_data": {}}
