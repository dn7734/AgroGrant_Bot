import os
import re
import json
import httpx

class LLMService:
    def __init__(self):
        self.models = [
            "gemini-2.0-flash",
            "gemini-2.5-flash",
            "gemini-flash-latest"
        ]
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()

    async def generate_response(self, user_message: str, current_profile: dict) -> dict:
        if not self.api_key:
            return {
                "reply": "Помилка конфігурації сервера. Відсутній ключ доступу.",
                "extracted_data": {},
                "is_error": True
            }

        system_instruction = (
            "Ти голосовий асистент АгроГрант. Твоя мета — зібрати дані про агропідприємство для грантової заявки. "
            "Спілкуйся виключно українською мовою, коротко, природно і без латинських абревіатур. "
            f"Поточний профіль підприємства: {json.dumps(current_profile, ensure_ascii=False)}. "
            "Витягни нові дані з повідомлення користувача та м'яко запитай про 1-2 наступні незаповнені поля. "
            "Коли всі поля заповнені, порекомендуй програму та повідоми, що заявку можна завантажити кнопкою нижче. "
            "ОБОВ'ЯЗКОВО повертай відповідь строго у форматі JSON з двома полями: "
            "'reply' (текст відповіді українською) та 'extracted_data' (словник із ключами: "
            "region, activity_type, size_category, employees_count, investment_focus, own_contribution_percent; "
            "значення — рядок або null)."
        )

        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
            "generationConfig": {"response_mime_type": "application/json"}
        }

        last_error = "невідома помилка"
        
        # Захист від падінь DNS на Render: автоматично робимо 3 спроби перепідключення
        transport = httpx.AsyncHTTPTransport(retries=3)

        async with httpx.AsyncClient(transport=transport) as client:
            for model_name in self.models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
                try:
                    # Збільшено таймаут до 30 секунд для важких мережевих умов
                    response = await client.post(url, headers=headers, json=payload, timeout=30.0)
                    print(f"Model {model_name} -> Status Code: {response.status_code}")

                    if response.status_code == 200:
                        data = response.json()
                        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        
                        text_response = ""
                        for part in parts:
                            if not part.get("thought") and "text" in part:
                                text_response = part["text"].strip()

                        if not text_response and parts:
                            text_response = parts[-1].get("text", "").strip()

                        # Надійний пошук JSON
                        match = re.search(r"\{.*\}", text_response, re.DOTALL)
                        json_str = match.group(0) if match else text_response

                        try:
                            parsed = json.loads(json_str)
                            if isinstance(parsed, list) and parsed:
                                parsed = parsed[0]
                            return {
                                "reply": parsed.get("reply", text_response or "Дані прийнято."),
                                "extracted_data": parsed.get("extracted_data", {}),
                                "is_error": False
                            }
                        except Exception as parse_err:
                            print(f"JSON parse fallback on {model_name}: {parse_err}")
                            return {
                                "reply": text_response or "Дані отримано, але формат відповіді порушено.",
                                "extracted_data": {},
                                "is_error": False
                            }
                    else:
                        last_error = f"код {response.status_code}"
                        print(f"API Error on {model_name}: {response.text}")
                except Exception as e:
                    last_error = f"{type(e).__name__}: {str(e)}"
                    print(f"Мережевий збій на {model_name}: {last_error}")
                    continue # Пробуємо наступну модель у списку

        return {
            "reply": f"Тимчасовий збій мережі на сервері. Будь ласка, спробуйте ще раз. ({last_error})",
            "extracted_data": {},
            "is_error": True
        }