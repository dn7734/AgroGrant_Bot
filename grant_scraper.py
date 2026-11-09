"""
НАУКОВО-МЕТОДИЧНИЙ ОПИС МОДУЛЯ (grant_scraper.py):
Модуль багатокритеріального скорингу інвестиційних та грантових моделей кластеризації.
Реалізує алгоритм ранжування неборгових фінансових інструментів (державні гранти на переробку,
венчурне партнерство Наука–Бізнес, форвардний Off-take пул) відповідно до профілю учасника.
"""

import re

DEFAULT_GRANTS = [
    {
        "code": "cluster_deep_processing",
        "title": "Біоекономічний кластер глибокої переробки (Олія, порошок, шрот)",
        "donor": "Мінекономіки / Провайдинг ТОВ «Інститут інноваційної біоекономіки»",
        "max_amount": "до 8 000 000 грн (безповоротно)",
        "min_own_percent": 20,
        "target_kveds": "10.41, 10.61, 10.84, 10.91",
        "land_req": "Виробничий цех / лінія холодного пресування олії",
        "keywords": ["перероб", "олійн", "олія", "порошок", "шрот", "екстракц", "лінія", "цех"],
        "requirements": "Інтеграція в ланцюг доданої вартості кластеру, безвідходна технологія Zero-Waste."
    },
    {
        "code": "cluster_white_princess_seed",
        "title": "Кластерний стартап «Біла Принцеса»: Базове та елітне насінництво",
        "donor": "ННЦ «Інститут землеробства НААН» / Бізнес-інкубатор ІІБ",
        "max_amount": "до 6 500 000 грн (венчурний пул)",
        "min_own_percent": 25,
        "target_kveds": "01.11, 01.64, 72.19",
        "land_req": "від 1 га (Супереліта) до 300 га (І репродукція)",
        "keywords": ["гірчиц", "біла принцеса", "насін", "супереліт", "еліт", "репродукц", "селекц", "зерн"],
        "requirements": "Ліцензійна угода з НУС НААН, авансове передзамовлення селекції та контроль чистоти."
    },
    {
        "code": "cluster_science_transfer",
        "title": "Експериментальний кластер трансферу ОІВ (Платформа Наука–Бізнес)",
        "donor": "НААН України / Венчурний фонд ІІБ",
        "max_amount": "до 5 000 000 грн",
        "min_own_percent": 15,
        "target_kveds": "72.11, 72.19, 70.22, 01.11",
        "land_req": "Дослідно-демонстраційний полігон від 1 га",
        "keywords": ["наук", "трансфер", "патент", "інновац", "драфт", "тизер", "кластер", "оів"],
        "requirements": "Внесення майнових прав інтелектуальної власності на сорт у статутний капітал кластеру."
    },
    {
        "code": "cluster_eco_siderat",
        "title": "Агроекологічний кластер сидерації та органічного землеробства",
        "donor": "Інститут землеробства НААН / Міжнародні еко-фонди",
        "max_amount": "до 4 500 000 грн",
        "min_own_percent": 30,
        "target_kveds": "01.11, 01.13, 01.61",
        "land_req": "від 50 до 500 га",
        "keywords": ["сидерат", "органіч", "біофумігац", "родюч", "еколог", "експорт"],
        "requirements": "Впровадження сівозмін із білою гірчицею для біофумігації та оздоровлення ґрунтів."
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
        score = 62
        reasons = []
        kw_list = g.get("keywords", [])
        if isinstance(kw_list, str):
            kw_list = [k.strip() for k in kw_list.split(",") if k.strip()]

        matched_kw = [kw for kw in kw_list if kw in combined_text]
        if matched_kw:
            score += 22
            reasons.append("Технологічна спеціалізація учасника збігається з ланкою кластеру")

        target_kveds = g.get("target_kveds", "")
        if kved and any(prefix.strip()[:4] in kved for prefix in target_kveds.split(",") if prefix.strip()):
            score += 10
            reasons.append("Основний КВЕД відповідає вимогам програми")

        min_own = float(g.get("min_own_percent") or 0)
        if own_pct >= min_own:
            score += 8
            reasons.append(f"Частка співфінансування покриває нормативний поріг ({int(min_own)}%)")
        elif own_pct > 0 and own_pct < min_own:
            score -= 8
            reasons.append(f"Мінімальний рекомендований внесок становить {int(min_own)}%")

        score = max(35, min(98, score))
        status = "Пріоритетна модель кластеру" if score >= 75 else "Доступно для кооперації"

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
            "reason": "; ".join(reasons) if reasons else "Базова відповідність критеріям трансферу технологій НААН–ІІБ"
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


async def scrape_and_normalize_grants(api_key: str = "") -> list:
    return DEFAULT_GRANTS
