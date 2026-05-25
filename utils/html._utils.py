# package
import re
import html


def sanitize_html(text: str, max_len: int = 0) -> str:
    """
    Убирает все HTML-теги кроме тех что понимает Telegram:
    <b>, <i>, <u>, <s>, <code>, <pre>, <a href="...">.
    Декодирует HTML-entities. Обрезает до max_len если задан.
    """
    if not text:
        return ""

    # Разрешённые теги Telegram
    ALLOWED = {"b", "i", "u", "s", "code", "pre"}

    # Удаляем все теги кроме разрешённых
    def replace_tag(m):
        tag = m.group(1).strip().lower().split()[0].lstrip("/")
        if tag in ALLOWED:
            return m.group(0)   # оставляем как есть
        return " "              # остальное — в пробел

    text = re.sub(r"<[^>]+>", replace_tag, text)

    # Декодируем &amp; &lt; и т.д.
    text = html.unescape(text)

    # Убираем множественные пробелы/переносы
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    text = text.strip()

    if max_len and len(text) > max_len:
        text = text[:max_len].rstrip() + "…"

    return text


def escape_html(text: str) -> str:
    """Экранирует < > & для безопасной вставки в HTML-сообщение."""
    return html.escape(str(text or ""))
