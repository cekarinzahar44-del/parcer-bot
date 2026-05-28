import aiosqlite
import json
from typing import Optional
from datetime import datetime

DB_PATH = "parser.db"

# ─── Типы источников ──────────────────────────────────────
SOURCE_TYPES = {
    "currency":  "💱 Курсы валют (ЦБ РФ)",
    "news":      "📰 Новости (RSS)",
    "github":    "🐙 GitHub Trending",
    "weather":   "🌤 Погода (wttr.in)",
    "custom":    "🔧 Свой URL (HTML)",
}

REPORT_FORMATS = ["xlsx", "csv", "json", "txt"]


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY,
                username   TEXT,
                full_name  TEXT,
                is_admin   INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Источники парсинга
            CREATE TABLE IF NOT EXISTS sources (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                name        TEXT NOT NULL,
                type        TEXT NOT NULL,
                config      TEXT NOT NULL,   -- JSON: url, keywords, filters, ...
                active      INTEGER DEFAULT 1,
                last_parsed TIMESTAMP,
                parse_count INTEGER DEFAULT 0,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            -- Спарсенные данные
            CREATE TABLE IF NOT EXISTS items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id   INTEGER NOT NULL,
                external_id TEXT,            -- уникальный ID из источника
                title       TEXT,
                url         TEXT,
                data        TEXT NOT NULL,   -- JSON с полными данными
                parsed_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_new      INTEGER DEFAULT 1,
                UNIQUE(source_id, external_id),
                FOREIGN KEY (source_id) REFERENCES sources(id)
            );

            -- Агрегированные метрики
            CREATE TABLE IF NOT EXISTS metrics (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id   INTEGER NOT NULL,
                metric_key  TEXT NOT NULL,   -- avg_salary, count, min, max, ...
                metric_val  REAL,
                metric_text TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id) REFERENCES sources(id)
            );

            -- Расписание авто-парсинга
            CREATE TABLE IF NOT EXISTS schedules (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id   INTEGER NOT NULL UNIQUE,
                interval_m  INTEGER NOT NULL DEFAULT 60,
                next_run    TIMESTAMP NOT NULL,
                enabled     INTEGER DEFAULT 1,
                FOREIGN KEY (source_id) REFERENCES sources(id)
            );

            -- Сгенерированные отчёты
            CREATE TABLE IF NOT EXISTS reports (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                source_id   INTEGER,
                format      TEXT NOT NULL,
                filename    TEXT NOT NULL,
                row_count   INTEGER,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id)   REFERENCES users(id),
                FOREIGN KEY (source_id) REFERENCES sources(id)
            );

            -- Лог операций
            CREATE TABLE IF NOT EXISTS parse_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id   INTEGER NOT NULL,
                status      TEXT NOT NULL,   -- ok | error | partial
                new_items   INTEGER DEFAULT 0,
                total_items INTEGER DEFAULT 0,
                error_msg   TEXT,
                duration_ms INTEGER,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id) REFERENCES sources(id)
            );
        """)
        await db.commit()


# ─── Пользователи ─────────────────────────────────────────

async def upsert_user(user_id: int, username: str, full_name: str, is_admin: bool = False):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO users (id, username, full_name, is_admin) VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET username=excluded.username,
               full_name=excluded.full_name""",
            (user_id, username or "", full_name, int(is_admin))
        )
        await db.commit()


# ─── Источники ────────────────────────────────────────────

async def create_source(user_id: int, name: str, stype: str, config: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO sources (user_id, name, type, config) VALUES (?, ?, ?, ?)",
            (user_id, name, stype, json.dumps(config, ensure_ascii=False))
        )
        await db.commit()
        return cur.lastrowid


async def get_sources(user_id: int, active_only: bool = False) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        where = "WHERE user_id = ?"
        params = [user_id]
        if active_only:
            where += " AND active = 1"
        cur = await db.execute(
            f"SELECT * FROM sources {where} ORDER BY created_at DESC", params
        )
        rows = await cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["config"] = json.loads(d["config"])
            result.append(d)
        return result


async def get_source(source_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM sources WHERE id = ?", (source_id,))
        row = await cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["config"] = json.loads(d["config"])
        return d


async def get_all_active_sources() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM sources WHERE active = 1")
        rows = await cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["config"] = json.loads(d["config"])
            result.append(d)
        return result


async def update_source_parsed(source_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sources SET last_parsed = CURRENT_TIMESTAMP, parse_count = parse_count + 1 WHERE id = ?",
            (source_id,)
        )
        await db.commit()


async def toggle_source(source_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT active FROM sources WHERE id = ?", (source_id,))
        row = await cur.fetchone()
        new_val = 1 - (row[0] if row else 0)
        await db.execute("UPDATE sources SET active = ? WHERE id = ?", (new_val, source_id))
        await db.commit()
        return bool(new_val)


async def delete_source(source_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM items WHERE source_id = ?", (source_id,))
        await db.execute("DELETE FROM metrics WHERE source_id = ?", (source_id,))
        await db.execute("DELETE FROM schedules WHERE source_id = ?", (source_id,))
        await db.execute("DELETE FROM parse_log WHERE source_id = ?", (source_id,))
        await db.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        await db.commit()


# ─── Данные (items) ───────────────────────────────────────

async def save_items(source_id: int, items: list[dict]) -> tuple[int, int]:
    """Сохраняет элементы, возвращает (new_count, total_count)"""
    new_count = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for item in items:
            try:
                await db.execute(
                    """INSERT INTO items (source_id, external_id, title, url, data)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(source_id, external_id) DO NOTHING""",
                    (
                        source_id,
                        item.get("id", item.get("title", "")[:100]),
                        item.get("title", "")[:500],
                        item.get("url", ""),
                        json.dumps(item, ensure_ascii=False)
                    )
                )
                if db.total_changes > 0:
                    new_count += 1
            except Exception:
                pass
        await db.commit()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM items WHERE source_id = ?", (source_id,))
        total = (await cur.fetchone())[0]

    return new_count, total


async def get_items(source_id: int, limit: int = 20, offset: int = 0,
                    search: str = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if search:
            cur = await db.execute(
                "SELECT * FROM items WHERE source_id = ? AND title LIKE ? ORDER BY parsed_at DESC LIMIT ? OFFSET ?",
                (source_id, f"%{search}%", limit, offset)
            )
        else:
            cur = await db.execute(
                "SELECT * FROM items WHERE source_id = ? ORDER BY parsed_at DESC LIMIT ? OFFSET ?",
                (source_id, limit, offset)
            )
        rows = await cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["data"] = json.loads(d["data"])
            result.append(d)
        return result


async def get_items_count(source_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM items WHERE source_id = ?", (source_id,))
        return (await cur.fetchone())[0]


async def get_all_items_for_export(source_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM items WHERE source_id = ? ORDER BY parsed_at DESC",
            (source_id,)
        )
        rows = await cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["data"] = json.loads(d["data"])
            result.append(d)
        return result


async def clear_items(source_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM items WHERE source_id = ?", (source_id,))
        await db.commit()


# ─── Метрики ──────────────────────────────────────────────

async def save_metrics(source_id: int, metrics: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        for key, val in metrics.items():
            if isinstance(val, (int, float)):
                await db.execute(
                    "INSERT INTO metrics (source_id, metric_key, metric_val) VALUES (?, ?, ?)",
                    (source_id, key, val)
                )
            else:
                await db.execute(
                    "INSERT INTO metrics (source_id, metric_key, metric_text) VALUES (?, ?, ?)",
                    (source_id, key, str(val))
                )
        await db.commit()


async def get_latest_metrics(source_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT metric_key,
                      MAX(recorded_at) as recorded_at,
                      metric_val, metric_text
               FROM metrics WHERE source_id = ?
               GROUP BY metric_key""",
            (source_id,)
        )
        rows = await cur.fetchall()
        result = {}
        for r in rows:
            result[r["metric_key"]] = r["metric_val"] if r["metric_val"] is not None else r["metric_text"]
        return result


async def get_metric_history(source_id: int, key: str, limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM metrics WHERE source_id = ? AND metric_key = ? ORDER BY recorded_at DESC LIMIT ?",
            (source_id, key, limit)
        )
        return [dict(r) for r in await cur.fetchall()]


# ─── Расписание ───────────────────────────────────────────

async def set_schedule(source_id: int, interval_m: int):
    from datetime import timedelta
    next_run = (datetime.now() + timedelta(minutes=interval_m)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO schedules (source_id, interval_m, next_run)
               VALUES (?, ?, ?)
               ON CONFLICT(source_id) DO UPDATE SET
               interval_m=excluded.interval_m, next_run=excluded.next_run, enabled=1""",
            (source_id, interval_m, next_run)
        )
        await db.commit()


async def get_due_schedules() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT sc.*, s.user_id, s.type, s.config, s.name
               FROM schedules sc
               JOIN sources s ON sc.source_id = s.id
               WHERE sc.enabled = 1
                 AND sc.next_run <= datetime('now')
                 AND s.active = 1"""
        )
        rows = await cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["config"] = json.loads(d["config"])
            result.append(d)
        return result


async def advance_schedule(schedule_id: int, interval_m: int):
    from datetime import timedelta
    next_run = (datetime.now() + timedelta(minutes=interval_m)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE schedules SET next_run = ? WHERE id = ?", (next_run, schedule_id)
        )
        await db.commit()


async def delete_schedule(source_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM schedules WHERE source_id = ?", (source_id,))
        await db.commit()


# ─── Отчёты ───────────────────────────────────────────────

async def save_report(user_id: int, source_id: int, fmt: str,
                       filename: str, row_count: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO reports (user_id, source_id, format, filename, row_count) VALUES (?, ?, ?, ?, ?)",
            (user_id, source_id, fmt, filename, row_count)
        )
        await db.commit()
        return cur.lastrowid


async def get_reports(user_id: int, limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT r.*, s.name as source_name FROM reports r
               LEFT JOIN sources s ON r.source_id = s.id
               WHERE r.user_id = ? ORDER BY r.created_at DESC LIMIT ?""",
            (user_id, limit)
        )
        return [dict(row) for row in await cur.fetchall()]


# ─── Лог ──────────────────────────────────────────────────

async def write_log(source_id: int, status: str, new_items: int = 0,
                     total_items: int = 0, error_msg: str = None, duration_ms: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO parse_log (source_id, status, new_items, total_items, error_msg, duration_ms) VALUES (?, ?, ?, ?, ?, ?)",
            (source_id, status, new_items, total_items, error_msg, duration_ms)
        )
        await db.commit()


async def get_logs(source_id: int, limit: int = 5) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM parse_log WHERE source_id = ? ORDER BY created_at DESC LIMIT ?",
            (source_id, limit)
        )
        return [dict(r) for r in await cur.fetchall()]


# ─── Общая статистика ─────────────────────────────────────

async def get_global_stats(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        sources = (await (await db.execute(
            "SELECT COUNT(*) FROM sources WHERE user_id = ?", (user_id,))).fetchone())[0]
        total_items = (await (await db.execute(
            "SELECT COUNT(*) FROM items i JOIN sources s ON i.source_id = s.id WHERE s.user_id = ?",
            (user_id,))).fetchone())[0]
        total_reports = (await (await db.execute(
            "SELECT COUNT(*) FROM reports WHERE user_id = ?", (user_id,))).fetchone())[0]
        last_parse = (await (await db.execute(
            "SELECT MAX(last_parsed) FROM sources WHERE user_id = ?", (user_id,))).fetchone())[0]
        return {
            "sources": sources,
            "total_items": total_items,
            "total_reports": total_reports,
            "last_parse": last_parse,
        }
