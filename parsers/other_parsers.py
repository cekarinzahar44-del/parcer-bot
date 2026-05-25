"""
Коллекция парсеров:
  - Курсы валют (ЦБ РФ XML)
  - GitHub Trending (HTML scraping)
  - RSS-новости (xml.etree)
  - Погода (wttr.in JSON)
"""
import aiohttp
import asyncio
from datetime import datetime
from xml.etree import ElementTree as ET
from html.parser import HTMLParser
import re
from utils.html_utils import sanitize_html, escape_html


# ═══════════════════════════════════════════════════════════
# 💱  КУРСЫ ВАЛЮТ — ЦБ РФ
# ═══════════════════════════════════════════════════════════

CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"

CURRENCY_NAMES = {
    "USD": "🇺🇸 Доллар США",
    "EUR": "🇪🇺 Евро",
    "CNY": "🇨🇳 Юань",
    "GBP": "🇬🇧 Фунт стерлингов",
    "JPY": "🇯🇵 Иена",
    "CHF": "🇨🇭 Франк",
    "TRY": "🇹🇷 Лира",
    "KZT": "🇰🇿 Тенге",
    "BYR": "🇧🇾 Белорусский рубль",
}


async def parse_currency(config: dict) -> tuple[list[dict], dict]:
    """
    config:
        codes - список валют, напр. ["USD","EUR","CNY"]
    """
    target_codes = config.get("codes", ["USD", "EUR", "CNY", "GBP"])

    async with aiohttp.ClientSession() as session:
        async with session.get(CBR_URL) as resp:
            xml_text = await resp.text(encoding="windows-1251")

    root = ET.fromstring(xml_text)
    date_str = root.attrib.get("Date", datetime.now().strftime("%d.%m.%Y"))

    items = []
    for valute in root.findall("Valute"):
        code = valute.findtext("CharCode", "")
        if code not in target_codes:
            continue
        nominal = int(valute.findtext("Nominal", "1"))
        value_str = valute.findtext("Value", "0").replace(",", ".")
        value = round(float(value_str) / nominal, 4)
        items.append({
            "id":      code,
            "title":   f"{code}/RUB",
            "code":    code,
            "name":    valute.findtext("Name", code),
            "nominal": nominal,
            "rate":    value,
            "date":    date_str,
            "url":     "https://cbr.ru",
        })

    metrics = {f"rate_{i['code']}": i["rate"] for i in items}
    metrics["as_of_date"] = date_str
    return items, metrics


def fmt_currency_item(item: dict) -> str:
    name = CURRENCY_NAMES.get(item["code"], item["name"])
    return (
        f"{name}\n"
        f"1 {item['code']} = <b>{item['rate']:,.4f} ₽</b>\n"
        f"📅 {item['date']}"
    )


# ═══════════════════════════════════════════════════════════
# 🐙  GITHUB TRENDING
# ═══════════════════════════════════════════════════════════

GITHUB_TRENDING_URL = "https://github.com/trending"


class _GithubParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.repos = []
        self._current = {}
        self._in_repo = False
        self._in_desc = False
        self._capture_h2 = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "article" and "Box" in attrs_dict.get("class", ""):
            self._in_repo = True
            self._current = {}
        if self._in_repo and tag == "h2":
            self._capture_h2 = True
        if self._in_repo and tag == "p":
            cls = attrs_dict.get("class", "")
            if "color-fg-muted" in cls:
                self._in_desc = True
        if self._in_repo and tag == "a" and self._capture_h2:
            href = attrs_dict.get("href", "")
            if href.count("/") == 2:
                self._current["url"] = "https://github.com" + href
                parts = href.strip("/").split("/")
                if len(parts) == 2:
                    self._current["owner"], self._current["repo"] = parts

    def handle_data(self, data):
        if self._in_desc:
            self._current["description"] = data.strip()
            self._in_desc = False

    def handle_endtag(self, tag):
        if tag == "h2":
            self._capture_h2 = False
        if tag == "article" and self._in_repo:
            self._in_repo = False
            if self._current.get("repo"):
                self.repos.append(self._current.copy())


async def parse_github(config: dict) -> tuple[list[dict], dict]:
    """
    config:
        language - фильтр языка (python, javascript, ...)
        since    - daily | weekly | monthly
    """
    lang  = config.get("language", "")
    since = config.get("since", "daily")
    url   = GITHUB_TRENDING_URL
    if lang:
        url += f"/{lang}"
    url += f"?since={since}"

    headers = {"User-Agent": "Mozilla/5.0 (ParserBot/1.0)"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as resp:
            html = await resp.text()

    parser = _GithubParser()
    parser.feed(html)
    repos = parser.repos[:25]

    items = []
    for i, r in enumerate(repos, 1):
        items.append({
            "id":          r.get("url", str(i)),
            "title":       f"{r.get('owner','')}/{r.get('repo','')}",
            "url":         r.get("url", ""),
            "owner":       r.get("owner", ""),
            "repo":        r.get("repo", ""),
            "description": r.get("description", ""),
            "rank":        i,
            "language":    lang or "all",
            "since":       since,
        })

    metrics = {
        "total_repos": len(items),
        "language":    lang or "all",
        "period":      since,
        "top_repo":    items[0]["title"] if items else "",
    }
    return items, metrics


def fmt_github_item(item: dict) -> str:
    return (
        f"#{item['rank']} 🐙 <b>{escape_html(item['title'])}</b>\n"
        f"📝 {escape_html(item.get('description','—')[:120])}\n"
        f"🔗 {item['url']}"
    )


# ═══════════════════════════════════════════════════════════
# 📰  RSS НОВОСТИ
# ═══════════════════════════════════════════════════════════

RSS_PRESETS = {
    "habr":    "https://habr.com/ru/rss/best/daily/?fl=ru",
    "rbc":     "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
    "lenta":   "https://lenta.ru/rss/news",
    "vc":      "https://vc.ru/rss",
    "tinkoff": "https://www.tinkoff.ru/feed/",
}


async def parse_news(config: dict) -> tuple[list[dict], dict]:
    """
    config:
        url      - RSS URL или ключ пресета (habr|rbc|lenta|vc)
        keywords - список ключевых слов для фильтрации
        limit    - кол-во новостей
    """
    url_or_key = config.get("url", "habr")
    url = RSS_PRESETS.get(url_or_key, url_or_key)
    keywords = [k.lower() for k in config.get("keywords", [])]
    limit = int(config.get("limit", 20))

    headers = {"User-Agent": "Mozilla/5.0 (ParserBot/1.0)"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            xml_text = await resp.text()

    root = ET.fromstring(xml_text)
    channel = root.find("channel") or root

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = channel.findall("item") or root.findall("atom:entry", ns)

    items = []
    for entry in entries[:limit * 2]:  # берём с запасом для фильтрации
        title = (entry.findtext("title") or
                 entry.findtext("atom:title", namespaces=ns) or "").strip()
        link  = (entry.findtext("link") or
                 entry.findtext("atom:link", namespaces=ns) or "")
        if hasattr(link, "strip"):
            link = link.strip()
        pub   = (entry.findtext("pubDate") or
                 entry.findtext("atom:published", namespaces=ns) or "")
        desc  = _strip_tags(entry.findtext("description") or
                            entry.findtext("atom:summary", namespaces=ns) or "")

        # Фильтр по ключевым словам
        if keywords:
            text_lower = (title + " " + desc).lower()
            if not any(k in text_lower for k in keywords):
                continue

        items.append({
            "id":          link or title[:80],
            "title":       title,
            "url":         link,
            "description": desc[:300],
            "published":   pub[:25],
        })
        if len(items) >= limit:
            break

    metrics = {
        "total_news": len(items),
        "source_url": url,
        "filtered_by": ", ".join(keywords) if keywords else "нет фильтра",
    }
    return items, metrics


def fmt_news_item(item: dict) -> str:
    pub = item.get("published", "")[:16]
    return (
        f"📰 <b>{escape_html(item['title'])}</b>\n"
        f"📅 {pub}\n"
        f"📝 {sanitize_html(item.get('description',''), 150)}\n"
        f"🔗 {item.get('url','')}"
    )


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


# ═══════════════════════════════════════════════════════════
# 🌤  ПОГОДА — wttr.in
# ═══════════════════════════════════════════════════════════

async def parse_weather(config: dict) -> tuple[list[dict], dict]:
    """
    config:
        city  - название города (на англ. или рус.)
        days  - кол-во дней прогноза (1-3)
    """
    city = config.get("city", "Moscow")
    days = min(int(config.get("days", 3)), 3)
    url  = f"https://wttr.in/{city}?format=j1"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()

    current = data["current_condition"][0]
    weather_descs = current.get("weatherDesc", [{}])
    desc_text = weather_descs[0].get("value", "") if weather_descs else ""

    items = []
    # Текущая погода
    items.append({
        "id":          f"{city}_now",
        "title":       f"Погода в {city} — сейчас",
        "url":         f"https://wttr.in/{city}",
        "temp_c":      int(current["temp_C"]),
        "feels_like":  int(current["FeelsLikeC"]),
        "humidity":    int(current["humidity"]),
        "wind_kmph":   int(current["windspeedKmph"]),
        "description": desc_text,
        "type":        "current",
        "city":        city,
    })

    # Прогноз по дням
    weather_icons = {"Sunny": "☀️", "Clear": "🌙", "Cloudy": "☁️",
                     "Rain": "🌧", "Snow": "❄️", "Fog": "🌫", "Thunder": "⛈"}

    for day_data in data.get("weather", [])[:days]:
        date_str = day_data.get("date", "")
        hourly = day_data.get("hourly", [])
        desc_list = day_data.get("weatherDesc", [{}])
        day_desc = desc_list[0].get("value", "") if desc_list else ""
        icon = next((v for k, v in weather_icons.items() if k in day_desc), "🌡")

        # Средние показатели за день
        temps = [int(h["tempC"]) for h in hourly]
        items.append({
            "id":          f"{city}_{date_str}",
            "title":       f"Прогноз {date_str} — {city}",
            "url":         f"https://wttr.in/{city}",
            "date":        date_str,
            "temp_max":    int(day_data.get("maxtempC", 0)),
            "temp_min":    int(day_data.get("mintempC", 0)),
            "description": day_desc,
            "icon":        icon,
            "type":        "forecast",
            "city":        city,
        })

    current_item = items[0]
    metrics = {
        "temp_c":       current_item["temp_c"],
        "feels_like":   current_item["feels_like"],
        "humidity":     current_item["humidity"],
        "wind_kmph":    current_item["wind_kmph"],
        "description":  desc_text,
    }
    return items, metrics


def fmt_weather_item(item: dict) -> str:
    if item["type"] == "current":
        return (
            f"🌡 <b>Сейчас в {escape_html(item['city'])}</b>\n"
            f"🌡 Температура: {item['temp_c']}°C (ощущается {item['feels_like']}°C)\n"
            f"💧 Влажность: {item['humidity']}%\n"
            f"💨 Ветер: {item['wind_kmph']} км/ч\n"
            f"☁️ {escape_html(item['description'])}"
        )
    else:
        return (
            f"{item.get('icon','🌡')} <b>{item['date']}</b> — {escape_html(item['city'])}\n"
            f"🌡 {item['temp_min']}°C ... {item['temp_max']}°C\n"
            f"☁️ {escape_html(item['description'])}"
        )
