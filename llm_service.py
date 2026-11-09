"""
Модуль когнітивного сервісу LLM (AgroGrant_Bot).
Оновлено до моделі gemini-3.8-flash згідно з вимогами API Google.
Включає локальний резервний NLU-парсер (Fallback) для захисту від ReadTimeout.
"""

import os
import re
import json
import httpx


class LLMService:
    """Клас асинхронної взаємодії з Gemini API та резервної екстракції параметрів АПК."""

    def __init__(self):
        # Використовуємо актуальну модель gemini-3.8-flash (усуває помилку 404 з логів Render)
        self.models = [
            "gemini-3.8-flash",
            "gemini-flash-latest"
        ]
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()

    def _local_fallback_extract(self, user_message: str, current_profile: dict) -> dict:
        """Локальний NLU-парсер на випадок таймауту мережі або відсутності ключа API."""
        msg_lower = user_message.lower()
        extracted = {}

        # Визначення регіону
        regions_map = {
            "вінниц": "Вінницька область",
            "київ": "Київська область",
            "черкас": "Черкаська область",
            "полтав": "Полтавська область",
            "львів": "Львівська область",
            "хмельниц": "Хмельницька область",
            "житомир": "Житомирська область",
            "дніпр": "Дніпропетровська область",
            "одес": "Одеська область",
            "харків": "Харківська область"
        }
        for kw, reg_name in regions_map.items():
            if kw in msg_lower:
                extracted["region"] = reg_name
                break

        # Визначення площі (га)
        ha_match = re.search(r"(\d+(?:[.,]\d+)?)\s*га\b", msg_lower)
        if ha_match:
            extracted["size_category"] = f"{ha_match.group(1)} га"

        # Визначення кількості працівників
        emp_match = re.search(r"(\d+)\s*(?:працівн|робітн|осіб|люд)", msg_lower)
        if emp_match:
            extracted["employees_count"] = f"{emp_match.group(1)} працівників"

        # Визначення власного внеску (%)
        pct_match = re.search(r"(\d{1,2})\s*%", msg_lower)
        if pct_match:
            extracted["own_contribution_percent"] = f"{pct_match.group(1)}%"

        # Визначення спеціалізації та інвестиційного фокусу
        if any(w in msg_lower for w in ["перероб", "олі", "млин", "шрот", "порошок", "ліні"]):
            extracted["activity_type"] = "Глибока агропереробка"
            extracted["investment_focus"] = "Обладнання для переробки агропродукції"
        elif any(w in msg_lower for w in ["сад", "ягід", "теплиц", "горіх"]):
            extracted["activity_type"] = "Садівництво та тепличне господарство"
            extracted["investment_focus"] = "Закладання саду / модульної теплиці"
        elif any(w in msg_lower for w in ["гірчиц", "насін", "зерн", "ріпак", "соя", "пшениц"]):
            extracted["activity_type"] = "Рослинництво та насінництво"
            extracted["investment_focus"] = "Масштабування посівів та сертифікація насіння"

        merged = {**current_profile, **{k: v for k, v in extracted.items() if v}}
        missing = []
        if not merged.get("region"):
            missing.append("область локалізації")
        if not merged.get("size_category"):
            missing.append("земельний банк (га) або потужність")
        if not merged.get("own_contribution_percent"):
            missing.append("частку власного співфінансування (%)")

        if missing:
            reply_text = (
                "Дані проаналізовано та додано до реєстраційної картки. "
                f"Для точного розрахунку грантового скорингу уточніть, будь ласка: {', '.join(missing[:2])}."
            )
        else:
            reply_text = (
                f"Профіль підприємства ({merged.get('company_name') or 'Агропідприємство'}) "
                "повністю сформовано. Нижче наведено ранжований перелік релевантних грантових програм. "
                "Ви можете вивантажити аналітичний звіт у форматі PDF або DOCX."
            )

        return {
            "reply": reply_text,
            "extracted_data": extracted,
            "is_error": False
        }

    async def generate_response(self, user_message: str, current_profile: dict) -> dict:
        """Генерація відповіді через Gemini 3.8 Flash з автоматичним переходом на локальний NLU."""
        if not self.api_key:
            return self._local_fallback_extract(user_message, current_profile)

        system_instruction = (
            "Ти — інтелектуальний асистент оцінки грантоспроможності аграрних підприємств України (AgroGrant Analytics). "
            "Спілкуйся українською мовою у фаховому консалтинговому стилі, лаконічно (2-4 речення). "
            f"Поточний профіль підприємства: {json.dumps(current_profile, ensure_ascii=False)}. "
            "Витягни нові параметри з повідомлення користувача та, якщо профіль неповний, запитай про 1-2 відсутні показники "
            "(регіон, площа в га, кількість працівників, інвестиційний фокус, власний внесок у %). "
            "Повертай відповідь СТРОГО у форматі JSON з двома полями: "
            "'reply' (текст відповіді) та 'extracted_data' (словник із ключами: "
            "region, activity_type, size_category, employees_count, investment_focus, own_contribution_percent)."
        )

        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
            "generationConfig": {"response_mime_type": "application/json"}
        }

        # Скорочений таймаут (12 с) унеможливлює зависання воркера Render (ReadTimeout)
        timeout_cfg = httpx.Timeout(12.0, connect=5.0)
        transport = httpx.AsyncHTTPTransport(retries=1)

        async with httpx.AsyncClient(transport=transport, timeout=timeout_cfg) as client:
            for model_name in self.models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
                try:
                    response = await client.post(url, headers=headers, json=payload)
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
                            "reply": parsed.get("reply", "Параметри підприємства оновлено."),
                            "extracted_data": parsed.get("extracted_data", {}),
                            "is_error": False
                        }
                except Exception:
                    continue

        # Якщо зовнішній API недоступний або перевищив ліміт очікування — працює локальний парсер
        return self._local_fallback_extract(user_message, current_profile)
