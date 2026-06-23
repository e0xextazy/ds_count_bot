"""Конфигурация из окружения, каталог МП и проверка доступа."""
import os
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

# Московское время (UTC+3) для всех меток времени и расписания
MSK = ZoneInfo("Europe/Moscow")

# ============ КОНФИГУРАЦИЯ ============
# Значения читаются из переменных окружения (см. .env / docker-compose.yml).
# Токен НИКОГДА не должен храниться в коде.
TOKEN = os.environ.get("DISCORD_TOKEN", "")
LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID", "0"))  # ID канала для логов (0 — логи в канал выключены)
TEST_GUILD_ID = int(os.environ.get("TEST_GUILD_ID", "0"))  # ID сервера для синхронизации слэш-команд


def _parse_bool(raw):
    """Превращает строку из env ('true'/'1'/'yes'/'on') в bool. По умолчанию False."""
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


# Экспорт результатов пересчёта в Google Sheets. По умолчанию выключен.
EXPORT_TO_SHEET = _parse_bool(os.environ.get("EXPORT2SHEET", "false"))


def _parse_user_ids(raw):
    """Парсит список user ID из строки вида '123, 456' в множество int."""
    ids = set()
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


# Доступ к боту: администраторы Discord + явно перечисленные пользователи (whitelist).
# ID через запятую в переменной окружения ALLOWED_USER_IDS (см. .env / docker-compose.yml).
ALLOWED_USER_IDS = _parse_user_ids(os.environ.get("ALLOWED_USER_IDS", ""))


def is_allowed(user):
    """True, если у участника право «Администратор» Discord или его ID в whitelist."""
    if user is None:
        return False
    if user.id in ALLOWED_USER_IDS:
        return True
    perms = getattr(user, "guild_permissions", None)
    return bool(perms and perms.administrator)


async def guard_interaction(interaction: "discord.Interaction") -> bool:
    """interaction_check для вью: пускает только админов и whitelist."""
    if is_allowed(interaction.user):
        return True
    await interaction.response.send_message(
        "⛔ У тебя нет доступа.", ephemeral=True
    )
    return False


def allowed_only():
    """Check для текстовых команд: только админы и whitelist."""
    async def predicate(ctx):
        return is_allowed(ctx.author)
    return commands.check(predicate)


# ============ КАТАЛОГ МП (МЕРОПРИЯТИЙ) ============
# Захардкоженный список мероприятий и их времени (МСК).
# Кнопками «Добавить МП» / «Убрать МП» включаются/выключаются МП,
# участвующие в запланированном пересчёте (data['enabled_events']).
EVENTS = {
    "Диллеры": ["10:55", "18:55"],
    "Цеха": ["14:55", "22:55"],
    "Дроп": ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00"],
}
