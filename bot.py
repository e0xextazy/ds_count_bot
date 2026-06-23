"""Точка входа: события, команды, инициализация и запуск бота.

Логика разнесена по модулям:
  • config   — константы, каталог МП, доступ;
  • storage  — состояние (voice_data.json);
  • client   — экземпляр bot и логирование;
  • counting — подсчёт по ролям и расписание МП;
  • recalc   — пересчёт и фоновая задача;
  • views    — кнопки/селекты админ-панели.
"""
import discord
from discord.ext import commands

import db
from config import TOKEN, TEST_GUILD_ID, is_allowed, allowed_only
from storage import data, DATA_FILE
from client import bot, log_to_channel
from counting import get_schedule_summary
from recalc import scheduled_recalc
from views import AdminPanelView


# ============ СОБЫТИЯ ============
@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} запущен!')
    print(f'📊 На серверах: {len(bot.guilds)}')

    for guild in bot.guilds:
        print(f"  - Сервер: {guild.name} (ID: {guild.id})")

    try:
        if TEST_GUILD_ID:
            guild = discord.Object(id=TEST_GUILD_ID)
            synced = await bot.tree.sync(guild=guild)
            print(f"✅ Синхронизировано команд для сервера: {len(synced)}")
            for cmd in synced:
                print(f"  - /{cmd.name}")
        else:
            synced = await bot.tree.sync()
            print(f"✅ Синхронизировано глобальных команд: {len(synced)}")
            for cmd in synced:
                print(f"  - /{cmd.name}")
    except Exception as e:
        print(f"❌ Ошибка синхронизации: {e}")

    if not scheduled_recalc.is_running():
        scheduled_recalc.start()

    await log_to_channel(f"🤖 Бот запущен! Отслеживается {sum(len(ch) for ch in data['voice_channels'].values())} каналов.")
    print("✅ Бот полностью готов к работе!")

@bot.event
async def on_error(event, *args, **kwargs):
    error_msg = f"❌ Ошибка в {event}: {args}"
    print(error_msg)
    await log_to_channel(error_msg)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    """Централизованное логирование ВСЕХ интеракций в PostgreSQL."""
    try:
        itype = interaction.type
        if itype == discord.InteractionType.application_command:
            event_type = "slash_command"
            detail = f"/{interaction.command.name if interaction.command else '?'}"
        elif itype == discord.InteractionType.component:
            event_type = "component"
            detail = (interaction.data or {}).get("custom_id", "?")
        elif itype == discord.InteractionType.modal_submit:
            event_type = "modal_submit"
            detail = (interaction.data or {}).get("custom_id", "?")
        else:
            event_type = str(itype)
            detail = ""

        await db.log_event(
            event_type=event_type,
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id,
            user_id=interaction.user.id if interaction.user else None,
            user_name=str(interaction.user) if interaction.user else None,
            detail=detail,
        )
    except Exception as e:
        print(f"⚠️ Ошибка логирования интеракции: {e}")

@bot.event
async def on_command(ctx):
    """Логирование текстовых команд (!admin, !panel, !sync)."""
    await db.log_event(
        event_type="text_command",
        guild_id=ctx.guild.id if ctx.guild else None,
        channel_id=ctx.channel.id if ctx.channel else None,
        user_id=ctx.author.id,
        user_name=str(ctx.author),
        detail=f"!{ctx.command.name if ctx.command else '?'}",
    )

# ============ СЛЕШ-КОМАНДЫ ============
@bot.tree.command(
    name="admin_panel",
    description="Открыть админ-панель управления",
    guild=discord.Object(id=TEST_GUILD_ID)
)
async def admin_panel(interaction: discord.Interaction):
    if not is_allowed(interaction.user):
        await interaction.response.send_message(
            "⛔ У тебя нет доступа к этой команде.", ephemeral=True
        )
        return

    embed = discord.Embed(
        title="⚙️ Админ панель",
        description="Управление голосовыми и сценическими каналами",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="⏰ Запланированные пересчёты (МП)",
        value=get_schedule_summary(),
        inline=False
    )

    embed.set_footer(text="Доступ: администраторы и разрешённые пользователи")

    view = AdminPanelView()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ============ ТЕКСТОВЫЕ КОМАНДЫ ============
@bot.command(name='admin')
@allowed_only()
async def admin_command(ctx):
    embed = discord.Embed(
        title="⚙️ Админ панель",
        description="Управление голосовыми и сценическими каналами",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="⏰ Запланированные пересчёты (МП)",
        value=get_schedule_summary(),
        inline=False
    )

    embed.set_footer(text="Доступ: администраторы и разрешённые пользователи")

    view = AdminPanelView()
    await ctx.send(embed=embed, view=view)

@bot.command(name='panel')
@allowed_only()
async def panel_command(ctx):
    await ctx.invoke(bot.get_command('admin'))

@bot.command(name='sync')
@commands.is_owner()
async def sync_commands(ctx):
    try:
        if TEST_GUILD_ID:
            guild = discord.Object(id=TEST_GUILD_ID)
            synced = await bot.tree.sync(guild=guild)
            await ctx.send(f"✅ Синхронизировано {len(synced)} команд для сервера")
        else:
            synced = await bot.tree.sync()
            await ctx.send(f"✅ Синхронизировано {len(synced)} глобальных команд")
    except Exception as e:
        await ctx.send(f"❌ Ошибка: {e}")

# ============ ИНИЦИАЛИЗАЦИЯ (setup_hook) ============
async def _setup_hook():
    # Подключение к PostgreSQL и создание таблиц логов
    await db.init_db()
    # Регистрируем persistent view, чтобы кнопки панели работали после перезапуска
    bot.add_view(AdminPanelView())

bot.setup_hook = _setup_hook

# ============ ЗАПУСК ============
if __name__ == "__main__":
    if not TOKEN:
        print("=" * 50)
        print("❌ ОШИБКА: Не указан токен бота!")
        print("Задайте переменную окружения DISCORD_TOKEN")
        print("(см. файл .env / docker-compose.yml)")
        print("=" * 50)
        exit(1)

    print("=" * 50)
    print("🚀 ЗАПУСК БОТА")
    print("=" * 50)
    print(f"📁 Файл данных: {DATA_FILE}")

    total_voice = sum(len(ch) for ch in data.get('voice_channels', {}).values())
    print(f"🔊 Отслеживаемых каналов: {total_voice}")
    print("=" * 50)

    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ ОШИБКА: Неверный токен бота! Проверьте DISCORD_TOKEN.")
        exit(1)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        exit(1)
