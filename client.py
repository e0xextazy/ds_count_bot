"""Экземпляр бота (intents) и помощники логирования."""
import discord
from discord.ext import commands

import db
from config import LOG_CHANNEL_ID

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)


async def log_to_channel(message=None, embed=None):
    """Отправляет лог в канал LOG_CHANNEL_ID.
    Можно передать только text (message), только embed, или оба."""
    if LOG_CHANNEL_ID:
        channel = bot.get_channel(LOG_CHANNEL_ID)
        if channel:
            try:
                if embed:
                    # Если есть embed, отправляем его (с текстом, если он передан)
                    await channel.send(content=message or "", embed=embed)
                else:
                    # Если embed нет, отправляем только текст (с префиксом [LOG])
                    await channel.send(f"[LOG] {message}")
            except discord.DiscordException as e:
                print(f"⚠️ Не удалось отправить лог в канал: {e}")


async def log_action(interaction, event_type, detail=None):
    """Семантическая запись действия пользователя в event_logs."""
    await db.log_event(
        event_type=event_type,
        guild_id=interaction.guild.id if interaction.guild else None,
        channel_id=interaction.channel.id if interaction.channel else None,
        user_id=interaction.user.id if interaction.user else None,
        user_name=str(interaction.user) if interaction.user else None,
        detail=detail,
    )
