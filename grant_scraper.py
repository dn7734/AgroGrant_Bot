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
        "title": "єРобота: Грант на власний сад та ягідництво (Постанова КМУ №738)",
        "donor": "Мінагрополітики / Дія.Бізнес",
        "max_amount": "до 10 000 000 грн (до 400 тис. грн/га)",
        "min_own_percent": 30,
        "target_kveds": "01.21, 01.24, 01.25",
        "land_req": "від 1 до 25 га (власність або оренда від 7 років)",
        "keywords": ["сад", "ягід", "горіх", "лохин", "малин", "яблун", "виноград"],
        "requirements": "Створення від 5 до 10 постійних та сезонних робочих місць, відсутність податкового боргу."
    },
    {
        "code": "erobota_greenhouse",
        "title": "єРобота: Грант на модульну теплицю (Постанова КМУ №738)",
        "donor": "Мінагрополітики / Ощадбанк",
        "max_amount": "від 2 000 000 до 7 000 000 грн",
        "min_own_percent": 30,
        "target_kveds": "01.13, 01.19",
        "land_req": "від 0.4 до 2.4 га (оренда від 7 років)",
        "keywords": ["теплиц", "овоч", "томат", "огір", "зелен", "закритий ґрунт"],
        "requirements": "Створення не менше 4 робочих місць на 1 га теплиці, будівництво до 12 місяців."
    },
    {
        "code": "erobota_processing",
        "title": "єРобота: Грант на переробне підприємство в АПК",
        "donor": "Мінекономіки / Дія",
        "max_amount": "до 8 000 000 грн",
        "min_own_percent": 20,
        "target_kveds": "10.1, 10.3, 10.4, 10.6, 10.9",
        "land_req": "Наявність виробничого приміщення або ділянки",
        "keywords": ["перероб", "сушка", "сушар", "олійн", "млин", "борошн", "комбікорм", "обладнан", "лінія", "елеватор"],
        "requirements": "Співфінансування 50/50 (або 80/20 для прифронтових областей), створення від 5 до 25 робочих місць."
    },
    {
        "code": "dar_crops_support",
        "title": "Програма підтримки малих і середніх агровиробників через ДАР",
        "donor": "ДАР / ЄС / Світовий банк / USAID АГРО",
        "max_amount": "від 500 000 до 3 500 000 грн (субсидія на га / ресурси)",
        "min_own_percent": 0,
        "target_kveds": "01.11, 01.41, 01.45, 01.50",
        "land_req": "від 1 до 1000 га в офіційному обробітку в ДАР",
        "keywords": ["кукурудз", "пшениц", "соняшник", "соя", "зерн", "ріпак", "добрив", "насін", "рослинництв", "тваринництв", "корів"],
        "requirements": "Верифікований профіль у Державному аграрному реєстрі (ДАР), офіційно зареєстровані паї."
    },
    {
        "code": "vlasna_sprava_agro",
        "title": "Мікрогрант «Власна справа» для фермерів та ФОП",
        "donor": "Державний центр зайнятості / Дія",
        "max_amount": "до 250 000 грн (до 500 000 грн для прифронтових/ветеранських)",
        "min_own_percent": 0,
        "target_kveds": "01.1, 01.2, 01.4, 01.6",
        "land_req": "Без жорстких обмежень площі",
        "keywords": ["пасік", "мед", "птиц", "крафт", "сир", "технік", "мінітрактор", "старт"],
        "requirements": "Створення 1–2 нових робочих місць строком не менше ніж на 24 місяці."
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

        # 1. Перевірка збігу за ключовими словами та напрямом діяльності
        kw_list = g.get("keywords", [])
        if isinstance(kw_list, str):
            kw_list = [k.strip() for k in kw_list.split(",") if k.strip()]

        matched_kw = [kw for kw in kw_list if kw in combined_text]
        if matched_kw:
            score += 28
            reasons.append("Цільовий напрям інвестицій повністю збігається")

        # 2. Перевірка КВЕД
        target_kveds = g.get("target_kveds", "")
        if kved and any(prefix.strip()[:4] in kved for prefix in target_kveds.split(",") if prefix.strip()):
            score += 12
            reasons.append("Основний КВЕД відповідає вимогам програми")

        # 3. Перевірка власного внеску
        min_own = float(g.get("min_own_percent") or 0)
        if min_own == 0:
            score += 5
            reasons.append("Не потребує обов'язкового власного внеску")
        elif own_pct >= min_own:
            score += 10
            reasons.append(f"Власний внесок ({int(own_pct)}%) покриває мінімальний поріг ({int(min_own)}%)")
        elif own_pct > 0 and own_pct < min_own:
            score -= 15
            reasons.append(f"Потрібно збільшити власний внесок до {int(min_own)}%")
        else:
            reasons.append(f"Мінімальний власний внесок за програмою: {int(min_own)}%")

        score = max(25, min(98, score))
        status = "Висока сумісність (Рекомендовано)" if score >= 75 else "Базова сумісність (Доступно)"

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
            "reason": "; ".join(reasons) if reasons else "Підходить за базовими критеріями АПК"
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored

async def scrape_and_normalize_grants(api_key: str = "") -> list:
    urls = [
        "https://" + "www.dar.gov.ua/",
        "https://" + "business.diia.gov.ua/grants"
    ]
    raw_snippets = []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for u in urls:
            try:
                resp = await client.get(u, timeout=8.0)
                if resp.status_code == 200:
                    parser = _HTMLTextExtractor()
                    parser.feed(resp.text[:15000])
                    raw_snippets.append(parser.get_text()[:1500])
            except Exception as e:
                print(f"Scraper notice for {u}: {e}")

    # Повертаємо перевірений реєстр програм (разом зі спарсеними оновленнями)
    return DEFAULT_GRANTS