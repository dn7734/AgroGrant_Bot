"""
Модуль багатокритеріального скорингу державних та міжнародних грантів (AgroGrant_Bot).
Розраховує відсоток відповідності (Score) підприємства умовам кожної програми.
"""

import re

DEFAULT_GRANTS = [
    {
        "code": "ye_robota_processing",
        "title": "Державний грант на переробне підприємство (Програма «єРобота»)",
        "donor": "Мінекономіки України / Дія.Бізнес",
        "max_amount": "до 8 000 000 грн",
        "min_own_percent": 20,
        "target_kveds": "10.41, 10.61, 10.84, 10.91, 10.39",
        "land_req": "Виробниче приміщення / лінія переробки",
        "keywords": ["перероб", "олі", "шрот", "порошок", "ліні", "обладнан", "цех", "млин", "біла принцеса"],
        "requirements": "Створення від 5 до 25 нових робочих місць, відсутність податкового боргу, співфінансування від 20%."
    },
    {
        "code": "usaid_agro_resilience",
        "title": "Співфінансування проєктів переробки, елеваторів та насінництва АПК",
        "donor": "Програма USAID АГРО / Міжнародні донори",
        "max_amount": "до 15 000 000 грн",
        "min_own_percent": 30,
        "target_kveds": "01.11, 01.61, 01.64, 10.41, 72.19",
        "land_req": "від 100 га або діючі потужності зберігання/переробки",
        "keywords": ["зерн", "насін", "супереліт", "еліт", "гірчиц", "кластер", "перероб", "експорт"],
        "requirements": "Юридична особа або ФОП (реєстрація >1 року), залучення малих фермерів у ланцюг доданої вартості."
    },
    {
        "code": "ye_robota_orchard_greenhouse",
        "title": "Грант на розвиток садівництва, ягідництва та модульних теплиць",
        "donor": "Мінагрополітики України / ДАР",
        "max_amount": "до 7 000 000 грн (до 400 тис. грн/га)",
        "min_own_percent": 30,
        "target_kveds": "01.13, 01.24, 01.25, 01.26",
        "land_req": "від 1 до 25 га у власності або оренді (від 7 років)",
        "keywords": ["сад", "ягід", "теплиц", "горіх", "лохин", "яблун", "полив", "зрошен"],
        "requirements": "Наявність затвердженого проєкту висадки насаджень або будівництва модульної теплиці."
    },
    {
        "code": "dar_micro_agro",
        "title": "Грантова підтримка малих агровиробників та інноваційного насінництва",
        "donor": "Європейський Союз / Державний аграрний реєстр (ДАР)",
        "max_amount": "до 1 500 000 грн",
        "min_own_percent": 15,
        "target_kveds": "01.11, 01.13, 01.41, 01.64",
        "land_req": "від 10 до 500 га",
        "keywords": ["фермер", "зерн", "насін", "сидерат", "гірчиц", "технік", "добрив"],
        "requirements": "Реєстрація у системі ДАР, прозора структура власності, позитивна кредитна та податкова історія."
    }
]


def _extract_number(val: str) -> float:
    if not val:
        return 0.0
    nums = re.findall(r"\d+(?:[.,]\d+)?", str(val))
    return float(nums[0].replace(",", ".")) if nums else 0.0


def evaluate_grants(profile_data: dict, grants: list = None) -> list:
    """Ранжування грантових програм за спаданням індексу відповідності (Score)."""
    catalog = grants if grants else DEFAULT_GRANTS
    activity = (profile_data.get("activity_type") or "").lower()
    focus = (profile_data.get("investment_focus") or "").lower()
    kved = (profile_data.get("kved") or "").lower()
    own_pct = _extract_number(profile_data.get("own_contribution_percent") or "")
    combined_text = f"{activity} {focus} {kved}"

    scored = []
    for g in catalog:
        score = 60
        reasons = []
        kw_list = g.get("keywords", [])
        if isinstance(kw_list, str):
            kw_list = [k.strip() for k in kw_list.split(",") if k.strip()]

        if any(kw in combined_text for kw in kw_list):
            score += 24
            reasons.append("Цільовий напрям інвестицій збігається")

        target_kveds = g.get("target_kveds", "")
        if kved and any(prefix.strip()[:4] in kved for prefix in target_kveds.split(",") if prefix.strip()):
            score += 10
            reasons.append("КВЕД відповідає умовам конкурсу")

        min_own = float(g.get("min_own_percent") or 0)
        if own_pct >= min_own:
            score += 8
            reasons.append(f"Власний внесок покриває поріг ({int(min_own)}%)")
        elif own_pct > 0 and own_pct < min_own:
            score -= 10
            reasons.append(f"Потрібно збільшити співфінансування до {int(min_own)}%")

        score = max(35, min(98, score))
        status = "Висока відповідність" if score >= 75 else "Потребує доопрацювання"

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
            "reason": "; ".join(reasons) if reasons else "Базова відповідність критеріям МСП АПК"
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored
