import re
import json
import httpx
from html.parser import HTMLParser

class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.chunks = []

    def handle_data(self, data):
        clean = data.strip()
        if clean:
            self.chunks.append(clean)

    def get_text(self) -> str:
        return " ".join(self.chunks)

DEFAULT_GRANTS = [
    {
        "code": "erobota_orchard",
        "title": "єРобота: Грант на власний сад та ягідництво",
        "donor": "Мінагрополітики / Дія",
        "max_amount": "до 10 000 000 грн",
        "min_own_percent": 30,
        "target_kveds": "01.21, 01.24, 01.25",
        "land_req": "від 1 до 25 га",
        "keywords": ["сад", "ягід", "горіх", "лохин", "малин", "яблун", "виноград"],
        "requirements": "Створення від 5 до 10 робочих місць."
    },
    {
        "code": "erobota_greenhouse",
        "title": "єРобота: Грант на модульну теплицю",
        "donor": "Мінагро / Ощадбанк",
        "max_amount": "до 7 000 000 грн",
        "min_own_percent": 30,
        "target_kveds": "01.13, 01.19",
        "land_req": "від 0.4 до 2.4 га",
        "keywords": ["теплиц", "овоч", "томат", "огір", "зелен"],
        "requirements": "Створення не менше 4 робочих місць на 1 га."
    },
    {
        "code": "erobota_processing",
        "title": "єРобота: Грант на переробне підприємство",
        "donor": "Мінекономіки / Дія",
        "max_amount": "до 8 000 000 грн",
        "min_own_percent": 20,
        "target_kveds": "10.1, 10.3, 10.4, 10.6, 10.9",
        "land_req": "Наявність приміщення/ділянки",
        "keywords": ["перероб", "сушка", "олійн", "млин", "борошн", "обладнан"],
        "requirements": "Співфінансування 50/50, від 5 до 25 робочих місць."
    }
]

def _extract_number(val: str) -> float:
    if not val:
        return 0.0
    nums = re.findall(r"\d+(?:[.,]\d+)?", str(val))
    if not nums:
        return 0.0
    return float(nums[0].replace(",", "."))

def evaluate_grants(profile_data: dict, grants: list = None) -> list:
    catalog = grants if grants else DEFAULT_GRANTS
    activity = (profile_data.get("activity_type") or "").lower()
    focus = (profile_data.get("investment_focus") or "").lower()
    kved = (profile_data.get("kved") or "").lower()
    own_pct = _extract_number(profile_data.get("own_contribution_percent") or "")
    combined_text = f"{activity} {focus} {kved}"

    scored = []
    for g in catalog:
        score = 55
        reasons = []

        kw_list = g.get("keywords", [])
        if isinstance(kw_list, str):
            kw_list = [k.strip() for k in kw_list.split(",") if k.strip()]

        matched_kw = [kw for kw in kw_list if kw in combined_text]
        if matched_kw:
            score += 28
            reasons.append("Цільовий напрям інвестицій збігається")

        target_kveds = g.get("target_kveds", "")
        if kved and any(prefix.strip()[:4] in kved for prefix in target_kveds.split(",") if prefix.strip()):
            score += 12
            reasons.append("КВЕД відповідає вимогам")

        min_own = float(g.get("min_own_percent") or 0)
        if min_own == 0:
            score += 5
            reasons.append("Не потребує внеску")
        elif own_pct >= min_own:
            score += 10
            reasons.append(f"Власний внесок покриває поріг ({int(min_own)}%)")
        elif own_pct > 0 and own_pct < min_own:
            score -= 15
            reasons.append(f"Потрібно збільшити внесок до {int(min_own)}%")

        score = max(25, min(98, score))
        status = "Рекомендовано" if score >= 75 else "Доступно"

        scored.append({
            "code": g.get("code"),
            "title": g.get("title"),
            "donor": g.get("donor"),
            "max_amount": g.get("max_amount"),
            "min_own_percent": int(min_own),
            "target_kveds": target_kveds,
            "land_req": g.get("land_req"),
            "requirements": g.get("requirements"),
            "score": score,
            "status": status,
            "reason": "; ".join(reasons) if reasons else "Підходить за базовими критеріями"
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored

async def scrape_and_normalize_grants(api_key: str = "") -> list:
    if not api_key:
        return DEFAULT_GRANTS

    urls = [
        "https://" + "www.dar.gov.ua/",
        "https://" + "business.diia.gov.ua/grants"
    ]
    raw_text = ""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for u in urls:
            try:
                resp = await client.get(u, timeout=12.0)
                if resp.status_code == 200:
                    parser = _HTMLTextExtractor()
                    parser.feed(resp.text[:15000]) # Беремо лише верхню частину сторінок для економії токенів
                    raw_text += parser.get_text()[:3000] + "\n\n"
            except Exception as e:
                print(f"Scraper error for {u}: {e}")

    if not raw_text.strip():
        return DEFAULT_GRANTS

    prompt = (
        "Ти фінансовий аналітик. Знайди у тексті нижче актуальні гранти для агробізнесу і поверни масив JSON. "
        "Поля: code (унікальна англійська назва без пробілів), title (назва), donor (донор), "
        "max_amount (сума текстом), min_own_percent (число, % внеску, 0 якщо немає), "
        "target_kveds (цільові КВЕДи через кому, напр. '01.11, 10.1'), land_req (вимоги до землі), "
        "keywords (масив ключових слів), requirements (короткі умови).\n\nТекст:\n" + raw_text
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=25.0)
            if resp.status_code == 200:
                data = resp.json()
                text_resp = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text_resp.startswith("```"):
                    text_resp = text_resp.strip("`").removeprefix("json").strip()
                parsed = json.loads(text_resp)
                if isinstance(parsed, list) and len(parsed) > 0:
                    existing_codes = {g["code"] for g in DEFAULT_GRANTS}
                    new_grants = [g for g in parsed if g.get("code") not in existing_codes]
                    return DEFAULT_GRANTS + new_grants
    except Exception as e:
        print(f"AI parsing error: {e}")

    return DEFAULT_GRANTS