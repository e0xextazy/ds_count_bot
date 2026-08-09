"""Полный пересчёт войсов и фоновая задача по расписанию МП."""
from datetime import datetime

import discord
from discord.ext import tasks

import db
import sheets
from config import MSK, EXPORT_TO_SHEET
from client import bot, log_to_channel
from storage import data, save_data, get_guild_role_ids
from counting import count_members_by_role, get_event_at_time


async def perform_full_recalc(guild_id, interaction=None, event_name=None):
    try:
        # Чем инициирован пересчёт: вручную из панели или по расписанию МП
        trigger = "manual" if interaction is not None else "scheduled"
        guild = bot.get_guild(int(guild_id))
        if not guild:
            print(f"❌ Сервер {guild_id} не найден")
            return

        today = datetime.now(MSK).strftime("%Y-%m-%d")
        current_time = datetime.now(MSK).strftime("%H:%M")

        # Кто инициировал пересчёт (для футера карточки)
        if interaction and interaction.user:
            triggered_by = f"Выполнил: {interaction.user.display_name}"
        else:
            triggered_by = "⏰ Плановый пересчёт по расписанию"

        # Заранее неизвестно, в каком войсе идёт игра, поэтому пересчитываем
        # ВСЕ голосовые каналы сервера, где есть подключённые участники.
        connected_channels = [
            ch for ch in guild.channels
            if isinstance(ch, (discord.VoiceChannel, discord.StageChannel)) and ch.members
        ]

        # Структура истории: history[guild][дата][время][channel_id] = {...}
        day_slot = data['history'].setdefault(str(guild_id), {}).setdefault(today, {})
        time_slot = day_slot.setdefault(current_time, {})

        # Войс с наибольшим числом людей — он пойдёт в Google Sheets и в DC-канал.
        # Остальные войсы тихо считаем и сохраняем в БД, без карточек в канал.
        best_total = -1
        best_roles = {}
        best_channel = None

        role_ids = get_guild_role_ids(guild_id)

        for channel in connected_channels:
            channel_id = str(channel.id)

            role_counts, total_members, members = count_members_by_role(channel, guild, role_ids)

            # Для истории в JSON оставляем компактный список тех, у кого есть роль
            members_info = [f"{m['name']} ({m['role']})" for m in members if m['role']]

            time_slot[channel_id] = {
                'total': total_members,
                'roles': role_counts,
                'members': members_info[:20],
            }

            # count_logs: агрегированный результат пересчёта по этому войсу
            await db.log_count(
                guild_id=guild_id,
                channel_id=channel_id,
                channel_name=channel.name,
                event_name=event_name,
                trigger=trigger,
                total=total_members,
                roles=role_counts,
            )

            # members_logs: поимённый состав войса на момент пересчёта
            await db.log_members([
                {
                    'guild_id': guild_id,
                    'channel_id': channel_id,
                    'channel_name': channel.name,
                    'event_name': event_name,
                    'trigger': trigger,
                    'member_id': m['id'],
                    'member_name': m['name'],
                    'member_login': m['login'],
                    'role_name': m['role'],
                }
                for m in members
            ])

            # Запоминаем войс с максимальным числом участников
            if total_members > best_total:
                best_total = total_members
                best_roles = role_counts
                best_channel = channel

        # В DC-канал отправляем карточку только по войсу-победителю
        if best_channel is not None:
            icon = "🎤" if isinstance(best_channel, discord.StageChannel) else "🔊"
            embed = discord.Embed(
                title=f"{icon} {best_channel.name}",
                description=f"📅 {datetime.now(MSK).strftime('%d.%m.%Y %H:%M')}",
                color=discord.Color.blue() if not isinstance(best_channel, discord.StageChannel) else discord.Color.purple()
            )

            embed.add_field(
                name="👥 Всего учтено",
                value=f"**{best_total}** человек",
                inline=False
            )

            sorted_roles = sorted(best_roles.items(), key=lambda x: x[1], reverse=True)
            for role_name, count in sorted_roles:
                embed.add_field(
                    name=f"👤 {role_name}",
                    value=f"{count} чел.",
                    inline=True
                )

            embed.set_footer(text=triggered_by)
            await log_to_channel(embed=embed)
        else:
            await log_to_channel("ℹ️ Ни в одном голосовом канале нет подключённых участников.")

        # Экспорт в Google Sheets — только для пересчётов в 10:55 и 18:55.
        # Лист = дата (ДД.ММ), два блока на лист (10:55 и 18:55).
        # В таблицу пишем пересчёт того войса, где было больше всего людей.
        if EXPORT_TO_SHEET and current_time in sheets.EVENT_TIMES:
            sheet_date = datetime.now(MSK).strftime("%d.%m")
            try:
                result = await sheets.update_event(
                    sheet_date, current_time, best_roles
                )
                if result:
                    await log_to_channel(
                        f"📗 Google Sheets обновлён "
                        f"(войс «{best_channel.name if best_channel else '—'}», {max(best_total, 0)} чел.): {result}"
                    )
            except Exception as e:
                print(f"⚠️ Ошибка экспорта в Google Sheets: {e}")
                await log_to_channel(f"⚠️ Ошибка экспорта в Google Sheets: {e}")

        save_data(data)

    except Exception as e:
        error_msg = f"Ошибка при пересчете: {e}"
        print(f"❌ {error_msg}")
        await log_to_channel(f"❌ {error_msg}")


# ============ ФОНОВЫЕ ЗАДАЧИ ============
@tasks.loop(minutes=1)
async def scheduled_recalc():
    now = datetime.now(MSK)
    current_time = now.strftime("%H:%M")

    event_name = get_event_at_time(current_time)
    if event_name:
        await log_to_channel(f"⏰ Запланированный пересчёт «{event_name}» в {current_time}")
        for guild_id in data['voice_channels'].keys():
            await perform_full_recalc(guild_id, event_name=event_name)


@scheduled_recalc.before_loop
async def before_scheduled():
    await bot.wait_until_ready()
    print("✅ Бот готов, запланированные пересчёты активны!")
