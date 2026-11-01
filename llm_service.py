import os
import json
import httpx

class LLMService:
    def __init__(self):
        self.models = [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
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
            "Витягни нові дані з повідомлення користувача та м'яко запитай про1-2 наступні незаповнені поля. "
            "Коли всі поля заповнені, повідоми, що грантову заявку сформовано і її можна завантажити кнопкою нижче. "
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

        try:
            async with httpx.AsyncClient() as client:
                last_status = None
                for model_name in self.models:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
                    response = await client.post(url, headers=headers, json=payload, timeout=25.0)
                    last_status = response.status_code
                    print(f"Model {model_name} -> Status Code: {response.status_code}")

                    if response.status_code == 200:
                        data = response.json()
                        text_response = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                        if text_response.startswith("```"):
                            text_response = text_response.strip("`").removeprefix("json").strip()
                        parsed = json.loads(text_response)
                        return {
                            "reply": parsed.get("reply", "Дані прийнято."),
                            "extracted_data": parsed.get("extracted_data", {}),
                            "is_error": False
                        }
                    elif response.status_code == 404:
                        continue
                    else:
                        print(f"API Error on {model_name}: {response.text}")
                        break

                return {
                    "reply": f"Сервіс штучного інтелекту повернув помилку, код {last_status}.",
                    "extracted_data": {},
                    "is_error": True
                }
        except Exception as e:
            print(f"LLM Exception: {e}")
            return {
                "reply": "Тимчасовий збій зв'язку із сервісом обробки мови.",
                "extracted_data": {},
                "is_error": True
            }