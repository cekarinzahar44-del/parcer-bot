import os

# ─── Все переменные задаются в панели BotHost ──────────────
# Settings → Environment Variables

BOT_TOKEN   = os.environ["BOT_TOKEN"]
ADMIN_IDS   = list(map(int, os.environ.get("ADMIN_IDS", "0").split(",")))

# Прокси для парсинга (опционально)
HTTP_PROXY  = os.environ.get("HTTP_PROXY", "")

# Интервал авто-парсинга в минутах
AUTO_PARSE_INTERVAL = int(os.environ.get("AUTO_PARSE_INTERVAL", "60"))

# Папка для отчётов (BotHost поддерживает запись в рабочую директорию)
REPORTS_DIR = "reports_output"

# Лимит записей на источник
MAX_RECORDS_PER_SOURCE = int(os.environ.get("MAX_RECORDS_PER_SOURCE", "500"))
