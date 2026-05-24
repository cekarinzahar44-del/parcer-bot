"""
Парсер HeadHunter через публичный API (без ключа).
Документация: https://github.com/hhru/api
"""
import aiohttp
import asyncio
from typing import Optional


HH_API = "https://api.hh.ru"
HEADERS = {"User-Agent": "Mozilla/5.0 (ParserBot/1.0)"}


async def parse_hh(config: dict) -> tuple[list[dict], dict]:
    """
    config:
        text       - поисковый запрос (напр. "Python разработчик")
        area       - ID региона (1=Москва, 2=СПб, 113=Россия)
        salary_from- минимальная зарплата
        experience - noExperience | between1And3 | between3And6 | moreThan6
        per_page   - кол-во результатов (макс 100)
    """
    params = {
        "text":     config.get("text", ""),
        "area":     config.get("area", 113),
        "per_page": min(int(config.get("per_page", 50)), 100),
        "only_with_salary": config.get("only_with_salary", False),
    }
    if config.get("salary_from"):
        params["salary"] = config["salary_from"]
    if config.get("experience"):
        params["experience"] = config["experience"]

    items = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(f"{HH_API}/vacancies", params=params) as resp:
            if resp.status != 200:
                raise ValueError(f"HH API вернул {resp.status}")
            raw = await resp.json()

        vacancies = raw.get("items", [])

        # Детали первых 20 вакансий (rate limit)
        for v in vacancies[:20]:
            try:
                async with session.get(f"{HH_API}/vacancies/{v['id']}") as r:
                    detail = await r.json()
                    salary = detail.get("salary") or {}
                    item = {
                        "id":          detail["id"],
                        "title":       detail["name"],
                        "url":         detail["alternate_url"],
                        "company":     detail.get("employer", {}).get("name", ""),
                        "city":        detail.get("area", {}).get("name", ""),
                        "salary_from": salary.get("from"),
                        "salary_to":   salary.get("to"),
                        "currency":    salary.get("currency", "RUR"),
                        "experience":  detail.get("experience", {}).get("name", ""),
                        "schedule":    detail.get("schedule", {}).get("name", ""),
                        "skills":      [s["name"] for s in detail.get("key_skills", [])],
                        "description": _strip_html(detail.get("description", ""))[:300],
                        "published":   detail.get("published_at", "")[:10],
                    }
                    items.append(item)
                await asyncio.sleep(0.25)
            except Exception:
                # Если детали не получили — берём из списка
                salary = v.get("salary") or {}
                items.append({
                    "id":          v["id"],
                    "title":       v["name"],
                    "url":         v["alternate_url"],
                    "company":     v.get("employer", {}).get("name", ""),
                    "city":        v.get("area", {}).get("name", ""),
                    "salary_from": salary.get("from"),
                    "salary_to":   salary.get("to"),
                    "currency":    salary.get("currency", "RUR"),
                    "experience":  "",
                    "skills":      [],
                    "published":   v.get("published_at", "")[:10],
                })

    metrics = _calc_hh_metrics(items)
    return items, metrics


def _calc_hh_metrics(items: list[dict]) -> dict:
    salaries = []
    for i in items:
        if i.get("salary_from"):
            salaries.append(i["salary_from"])
        if i.get("salary_to"):
            salaries.append(i["salary_to"])

    metrics = {"total_vacancies": len(items)}
    if salaries:
        metrics["avg_salary"]  = round(sum(salaries) / len(salaries))
        metrics["min_salary"]  = min(salaries)
        metrics["max_salary"]  = max(salaries)
        metrics["median_salary"] = sorted(salaries)[len(salaries) // 2]

    # Топ навыков
    from collections import Counter
    all_skills = []
    for i in items:
        all_skills.extend(i.get("skills", []))
    top = Counter(all_skills).most_common(5)
    metrics["top_skills"] = ", ".join(f"{s}({c})" for s, c in top)

    # Распределение по опыту
    exp_counter = Counter(i.get("experience", "?") for i in items)
    for exp, cnt in exp_counter.most_common(3):
        if exp:
            metrics[f"exp_{exp[:20]}"] = cnt

    return metrics


def _strip_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", " ", text).strip()


def fmt_hh_item(item: dict) -> str:
    salary_str = "не указана"
    if item.get("salary_from") and item.get("salary_to"):
        salary_str = f"{item['salary_from']:,} – {item['salary_to']:,} {item.get('currency','RUR')}"
    elif item.get("salary_from"):
        salary_str = f"от {item['salary_from']:,} {item.get('currency','RUR')}"
    elif item.get("salary_to"):
        salary_str = f"до {item['salary_to']:,} {item.get('currency','RUR')}"

    skills = ", ".join(item.get("skills", [])[:5]) or "—"
    return (
        f"💼 <b>{item['title']}</b>\n"
        f"🏢 {item.get('company','')}\n"
        f"📍 {item.get('city','')}\n"
        f"💰 {salary_str}\n"
        f"🎓 {item.get('experience','')}\n"
        f"🛠 {skills}\n"
        f"🔗 {item.get('url','')}"
    )
