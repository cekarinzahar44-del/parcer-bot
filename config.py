import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN    = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
ADMIN_IDS    = list(map(int, os.getenv("ADMIN_IDS", "123456789").split(",")))

# Опционально: прокси для парсинга
HTTP_PROXY   = os.getenv("HTTP_PROXY", "")

# Интервал авто-парсинга (минуты)
AUTO_PARSE_INTERVAL = int(os.getenv("AUTO_PARSE_INTERVAL", "60"))

# Папка для хранения отчётов
REPORTS_DIR  = "reports_output"

# Лимит записей для хранения в БД на один источник
MAX_RECORDS_PER_SOURCE = int(os.getenv("MAX_RECORDS_PER_SOURCE", "500"))
