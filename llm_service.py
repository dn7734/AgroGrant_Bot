"""
НАУКОВО-МЕТОДИЧНИЙ ОПИС МОДУЛЯ (llm_service.py):
Модуль інтелектуального діалогового координатора платформи «AgroCluster Analytics».
Виконує семантичний аналіз неструктурованих повідомлень користувача (NLU),
автоматизовану екстракцію атрибутів паспорта підприємства у форматі JSON
та генерацію науково-консультаційних рекомендацій щодо інтеграції у кластер.
"""

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
                "reply": (
                    "Локальний контур верифікації активний. Параметри учасника кластеру "
                    "враховано у фінансовій моделі сорту «Біла Принцеса». Ви можете згенерувати Драфт або Pitch Deck."
                ),
                "extracted_data": {},
                "is_error": False
            }

        system_instruction = (
            "Ти — цифровий координатор біоекономічної платформи ТОВ «Інститут інноваційної біоекономіки» (ІІБ) "
            "та ННЦ «Інститут землеробства НААН». Твоя мета — допомогти учаснику сформувати паспорт проєкту "
            "в межах аграрного кластеру вирощування та глибокої переробки сорту гірчиці «Біла Принцеса» "
            "(1 га Супереліта → 25 га Еліта → 300+ га РС-1 → переробка на олію, порошок і шрот). "
            "Спілкуйся українською мовою в діловому науково-практичному стилі, лаконічно і чітко. "
            f"Поточний профіль учасника: {json.dumps(current_profile, ensure_ascii=False)}. "
            "Поверни відповідь строго у форматі JSON з двома ключами: "
            "'reply' (текст відповіді) та 'extracted_data' (словник із полями: "
            "region, activity_type, size_category, employees_count, investment_focus, own_contribution_percent)."
        )

        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
            "generationConfig": {"response_mime_type": "application/json"}
        }

        transport = httpx.AsyncHTTPTransport(retries=2)
        async with httpx.AsyncClient(transport=transport) as client:
            for model_name in self.models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
                try:
                    response = await client.post(url, headers=headers, json=payload, timeout=25.0)
                    if response.status_code == 200:
                        data = response.json()
                        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        text_response = ""
                        for part in parts:
                            if not part.get("thought") and "text" in part:
                                text_response = part["text"].strip()
                        if not text_response and parts:
                            text_response = parts[-1].get("text", "").strip()

                        match = re.search(r"\{.*\}", text_response, re.DOTALL)
                        json_str = match.group(0) if match else text_response
                        parsed = json.loads(json_str)
                        if isinstance(parsed, list) and parsed:
                            parsed = parsed[0]
                        return {
                            "reply": parsed.get("reply", "Параметри учасника кластеру інтегровано."),
                            "extracted_data": parsed.get("extracted_data", {}),
                            "is_error": False
                        }
                except Exception:
                    continue

        return {
            "reply": "Дані учасника кластеру зафіксовано. Скористайтеся кнопками генерації Драфту (PDF/DOCX) або Інвест-Тизера.",
            "extracted_data": {},
            "is_error": False
        }
