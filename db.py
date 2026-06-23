"""Логирование работы бота в PostgreSQL (asyncpg).

Три таблицы:
  • event_logs   — любое действие с ботом (кнопки, селекты, команды);
  • count_logs   — результат каждого пересчёта по каждому войсу;
  • members_logs — поимённый состав участников на момент пересчёта.
"""
import json
import os

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_pool: asyncpg.Pool | None = None


async def init_db():
    """Создаёт пул соединений и таблицы логов. Если DATABASE_URL не задан — БД отключена."""
    global _pool
    if not DATABASE_URL:
        print("ℹ️  DATABASE_URL не задан — логирование в PostgreSQL отключено.")
        return None

    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with _pool.acquire() as conn:
        # ---- event_logs: любое действие с ботом ----
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_logs (
                id          BIGSERIAL PRIMARY KEY,
                event_type  TEXT        NOT NULL,
                guild_id    TEXT,
                channel_id  TEXT,
                user_id     TEXT,
                user_name   TEXT,
                detail      TEXT,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_event_logs_created_at ON event_logs (created_at)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_event_logs_type ON event_logs (event_type)"
        )

        # ---- count_logs: результат каждого пересчёта по войсу ----
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS count_logs (
                id            BIGSERIAL PRIMARY KEY,
                guild_id      TEXT,
                channel_id    TEXT,
                channel_name  TEXT,
                event_name    TEXT,
                trigger       TEXT,
                total         INTEGER     NOT NULL DEFAULT 0,
                roles         JSONB,
                created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_count_logs_created_at ON count_logs (created_at)"
        )

        # ---- members_logs: поимённый состав на момент пересчёта ----
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS members_logs (
                id            BIGSERIAL PRIMARY KEY,
                guild_id      TEXT,
                channel_id    TEXT,
                channel_name  TEXT,
                event_name    TEXT,
                trigger       TEXT,
                member_id     TEXT,
                member_name   TEXT,
                member_login  TEXT,
                role_name     TEXT,
                created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_members_logs_created_at ON members_logs (created_at)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_members_logs_member_id ON members_logs (member_id)"
        )

    print("✅ PostgreSQL подключён, таблицы event_logs / count_logs / members_logs готовы.")
    return _pool


async def log_event(event_type, guild_id=None, channel_id=None,
                    user_id=None, user_name=None, detail=None):
    """event_logs: одно действие с ботом. Безопасна при отключённой БД и при сбоях."""
    if _pool is None:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO event_logs
                    (event_type, guild_id, channel_id, user_id, user_name, detail)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                event_type,
                str(guild_id) if guild_id is not None else None,
                str(channel_id) if channel_id is not None else None,
                str(user_id) if user_id is not None else None,
                user_name,
                detail,
            )
    except Exception as e:  # БД не должна ронять бота
        print(f"⚠️ Ошибка записи в event_logs: {e}")


async def log_count(guild_id, channel_id, channel_name, event_name, trigger, total, roles):
    """count_logs: результат пересчёта по одному войсу."""
    if _pool is None:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO count_logs
                    (guild_id, channel_id, channel_name, event_name, trigger, total, roles)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                """,
                str(guild_id) if guild_id is not None else None,
                str(channel_id) if channel_id is not None else None,
                channel_name,
                event_name,
                trigger,
                int(total),
                json.dumps(roles or {}, ensure_ascii=False),
            )
    except Exception as e:
        print(f"⚠️ Ошибка записи в count_logs: {e}")


async def log_members(members):
    """members_logs: пакетная запись участников на момент пересчёта.

    members — список словарей с ключами:
        guild_id, channel_id, channel_name, event_name, trigger,
        member_id, member_name, member_login, role_name
    """
    if _pool is None or not members:
        return
    try:
        rows = [
            (
                str(m.get("guild_id")) if m.get("guild_id") is not None else None,
                str(m.get("channel_id")) if m.get("channel_id") is not None else None,
                m.get("channel_name"),
                m.get("event_name"),
                m.get("trigger"),
                str(m.get("member_id")) if m.get("member_id") is not None else None,
                m.get("member_name"),
                m.get("member_login"),
                m.get("role_name"),
            )
            for m in members
        ]
        async with _pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO members_logs
                    (guild_id, channel_id, channel_name, event_name, trigger,
                     member_id, member_name, member_login, role_name)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                rows,
            )
    except Exception as e:
        print(f"⚠️ Ошибка записи в members_logs: {e}")


async def close_db():
    if _pool is not None:
        await _pool.close()
