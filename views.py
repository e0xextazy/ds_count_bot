"""Кнопки и селекты админ-панели (View / Select / Button)."""
from datetime import datetime, timedelta

import discord

from config import EVENTS, MSK, guard_interaction
from storage import data, save_data
from client import log_to_channel, log_action
from recalc import perform_full_recalc


# ============ АДМИН-ПАНЕЛЬ ============
class AdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await guard_interaction(interaction)

    @discord.ui.button(label="📊 Пересчет всех", style=discord.ButtonStyle.primary, custom_id="start_recalc", row=0)
    async def start_recalc_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild.id)

        has_channels = False
        if guild_id in data['voice_channels'] and data['voice_channels'][guild_id]:
            has_channels = True

        if has_channels:
            await log_action(interaction, "recalc_manual")
            await perform_full_recalc(guild_id, interaction)
            await interaction.followup.send("✅ Полный пересчет выполнен! Результаты отправлены в этот канал.", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ Нет настроенных каналов!", ephemeral=True)

    @discord.ui.button(label="🔊 Добавить войс", style=discord.ButtonStyle.success, custom_id="add_voice", row=1)
    async def add_voice_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = AddChannelView(interaction.guild)
        await interaction.response.send_message("Выберите голосовой или сценический канал:", view=view, ephemeral=True)

    @discord.ui.button(label="🔇 Убрать войс", style=discord.ButtonStyle.danger, custom_id="remove_voice", row=1)
    async def remove_voice_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RemoveChannelView(interaction.guild)
        await interaction.response.send_message("Выберите войс, который убрать из отслеживания:", view=view, ephemeral=True)

    @discord.ui.button(label="👤 Добавить роль", style=discord.ButtonStyle.success, custom_id="add_role", row=2)
    async def add_role_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = AddRoleView(interaction.guild)
        await interaction.response.send_message("Выберите роль для подсчёта:", view=view, ephemeral=True)

    @discord.ui.button(label="👤 Убрать роль", style=discord.ButtonStyle.danger, custom_id="remove_role", row=2)
    async def remove_role_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RemoveRoleView(interaction.guild)
        await interaction.response.send_message("Выберите роль, которую убрать из подсчёта:", view=view, ephemeral=True)

    @discord.ui.button(label="🗓️ Добавить МП", style=discord.ButtonStyle.success, custom_id="add_event", row=3)
    async def add_event_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = AddEventView()
        await interaction.response.send_message("Выберите МП для включения в расписание:", view=view, ephemeral=True)

    @discord.ui.button(label="🗓️ Убрать МП", style=discord.ButtonStyle.danger, custom_id="remove_event", row=3)
    async def remove_event_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RemoveEventView()
        await interaction.response.send_message("Выберите МП для исключения из расписания:", view=view, ephemeral=True)

    @discord.ui.button(label="📅 Выбрать дату", style=discord.ButtonStyle.secondary, custom_id="select_date", row=4)
    async def select_date_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = DatePickerView()
        await interaction.response.send_message("Выберите дату для просмотра результатов:", view=view, ephemeral=True)

    @discord.ui.button(label="📈 История", style=discord.ButtonStyle.gray, custom_id="show_history", row=4)
    async def show_history_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        embed = discord.Embed(
            title="📈 История проверок",
            color=discord.Color.gold()
        )

        has_data = False
        if guild_id in data['history'] and data['history'][guild_id]:
            has_data = True
            history_items = list(data['history'][guild_id].items())[-5:]
            for date_str, results in history_items:
                times = ", ".join(sorted(results.keys())) or "—"
                embed.add_field(
                    name=f"📅 {date_str}",
                    value=f"Снимков: {len(results)} ({times})",
                    inline=False
                )

        if has_data:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("📭 История пуста!", ephemeral=True)

# ============ ДОБАВЛЕНИЕ КАНАЛОВ ============
class AddChannelView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=60)
        select = AddChannelSelect(guild)
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await guard_interaction(interaction)

class AddChannelSelect(discord.ui.Select):
    def __init__(self, guild):
        self.guild = guild
        options = []

        for channel in guild.voice_channels:
            category_name = channel.category.name if channel.category else "Без категории"
            options.append(
                discord.SelectOption(
                    label=f"🔊 {channel.name} [{category_name}]",
                    value=f"voice_{channel.id}",
                    description=f"👥 {len(channel.members)} чел."
                )
            )

        for channel in guild.stage_channels:
            category_name = channel.category.name if channel.category else "Без категории"
            speakers = len(channel.members)
            options.append(
                discord.SelectOption(
                    label=f"🎤 {channel.name} [{category_name}]",
                    value=f"stage_{channel.id}",
                    description=f"👥 {speakers} чел. на сцене"
                )
            )

        if not options:
            options.append(
                discord.SelectOption(
                    label="❌ Нет доступных каналов",
                    value="none",
                    default=True
                )
            )

        if len(options) > 25:
            options = options[:25]

        super().__init__(placeholder="Выберите голосовой или сценический канал...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("⚠️ Нет доступных каналов!", ephemeral=True)
            return

        value = self.values[0]
        parts = value.split('_')
        channel_type = parts[0]
        identifier = '_'.join(parts[1:])

        guild_id = str(interaction.guild.id)

        channel = self.guild.get_channel(int(identifier))
        if not channel:
            await interaction.response.send_message("❌ Канал не найден!", ephemeral=True)
            return

        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            await interaction.response.send_message("❌ Это не голосовой и не сценический канал!", ephemeral=True)
            return

        key = 'voice_channels'

        if guild_id not in data[key]:
            data[key][guild_id] = []

        if identifier not in data[key][guild_id]:
            data[key][guild_id].append(identifier)
            save_data(data)

            channel_type_name = "сценический" if isinstance(channel, discord.StageChannel) else "голосовой"
            await interaction.response.send_message(
                f"✅ {channel_type_name.capitalize()} канал '{channel.name}' добавлен!",
                ephemeral=True
            )
            await log_to_channel(f"🔊 Добавлен {channel_type_name} канал '{channel.name}' ({identifier}) пользователем {interaction.user.name}")
            await log_action(interaction, "add_voice", detail=f"{channel.name} ({identifier})")
        else:
            await interaction.response.send_message("⚠️ Этот канал уже добавлен!", ephemeral=True)

# ============ УДАЛЕНИЕ КАНАЛОВ ============
class RemoveChannelView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=60)
        select = RemoveChannelSelect(guild)
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await guard_interaction(interaction)

class RemoveChannelSelect(discord.ui.Select):
    def __init__(self, guild):
        self.guild = guild
        options = []
        guild_id = str(guild.id)

        if guild_id in data['voice_channels']:
            for channel_id in data['voice_channels'][guild_id]:
                channel = guild.get_channel(int(channel_id))
                if channel:
                    channel_type = "🎤 Сценический" if isinstance(channel, discord.StageChannel) else "🔊 Голосовой"
                    category_name = channel.category.name if channel.category else "Без категории"
                    options.append(
                        discord.SelectOption(
                            label=f"{channel_type} {channel.name}",
                            value=f"remove_{channel_id}",
                            description=f"{category_name}"
                        )
                    )

        if not options:
            options.append(discord.SelectOption(label="Нет добавленных каналов", value="none", default=True))

        super().__init__(
            placeholder="Выберите войс, который убрать из отслеживания...",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("⚠️ Нет войсов для удаления из отслеживания!", ephemeral=True)
            return

        identifier = self.values[0].replace('remove_', '')
        guild_id = str(interaction.guild.id)

        if guild_id in data['voice_channels'] and identifier in data['voice_channels'][guild_id]:
            channel = self.guild.get_channel(int(identifier))
            data['voice_channels'][guild_id].remove(identifier)

            if not data['voice_channels'][guild_id]:
                del data['voice_channels'][guild_id]

            save_data(data)

            await interaction.response.send_message(f"✅ Войс убран из отслеживания!", ephemeral=True)
            await log_to_channel(f"🔇 Войс убран из отслеживания пользователем {interaction.user.name}")
            await log_action(interaction, "remove_voice", detail=f"{channel.name if channel else '?'} ({identifier})")
        else:
            await interaction.response.send_message("⚠️ Канал не найден!", ephemeral=True)

# ============ ДОБАВЛЕНИЕ РОЛЕЙ ============
class AddRoleView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=60)
        self.add_item(AddRoleSelect(guild))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await guard_interaction(interaction)

class AddRoleSelect(discord.ui.Select):
    def __init__(self, guild):
        self.guild = guild
        guild_id = str(guild.id)
        already = set(data['roles'].get(guild_id, []))
        options = []

        # Роли сверху вниз по иерархии, без @everyone и управляемых (ботских) ролей
        for role in sorted(guild.roles, key=lambda r: r.position, reverse=True):
            if role.is_default() or role.managed:
                continue
            if str(role.id) in already:
                continue  # уже добавлена — не предлагаем повторно
            options.append(
                discord.SelectOption(
                    label=f"👤 {role.name}",
                    value=f"role_{role.id}",
                    description=f"👥 {len(role.members)} чел."
                )
            )

        if not options:
            options.append(
                discord.SelectOption(label="❌ Нет доступных ролей", value="none", default=True)
            )

        if len(options) > 25:
            options = options[:25]

        super().__init__(placeholder="Выберите роль...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("⚠️ Нет доступных ролей!", ephemeral=True)
            return

        identifier = self.values[0].replace('role_', '')
        guild_id = str(interaction.guild.id)

        role = self.guild.get_role(int(identifier))
        if not role:
            await interaction.response.send_message("❌ Роль не найдена!", ephemeral=True)
            return

        if guild_id not in data['roles']:
            data['roles'][guild_id] = []

        if identifier not in data['roles'][guild_id]:
            data['roles'][guild_id].append(identifier)
            save_data(data)
            await interaction.response.send_message(
                f"✅ Роль '{role.name}' добавлена в подсчёт!", ephemeral=True
            )
            await log_to_channel(f"👤 Добавлена роль '{role.name}' ({identifier}) пользователем {interaction.user.name}")
            await log_action(interaction, "add_role", detail=f"{role.name} ({identifier})")
        else:
            await interaction.response.send_message("⚠️ Эта роль уже добавлена!", ephemeral=True)

# ============ УДАЛЕНИЕ РОЛЕЙ ============
class RemoveRoleView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=60)
        self.add_item(RemoveRoleSelect(guild))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await guard_interaction(interaction)

class RemoveRoleSelect(discord.ui.Select):
    def __init__(self, guild):
        self.guild = guild
        options = []
        guild_id = str(guild.id)

        if guild_id in data['roles']:
            for role_id in data['roles'][guild_id]:
                role = guild.get_role(int(role_id))
                label = role.name if role else f"Роль {role_id}"
                options.append(
                    discord.SelectOption(
                        label=f"👤 {label}",
                        value=f"remove_{role_id}",
                        description=(f"👥 {len(role.members)} чел." if role else "роль не найдена на сервере")
                    )
                )

        if not options:
            options.append(discord.SelectOption(label="Нет добавленных ролей", value="none", default=True))

        super().__init__(
            placeholder="Выберите роль, которую убрать из подсчёта...",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("⚠️ Нет ролей для удаления из подсчёта!", ephemeral=True)
            return

        identifier = self.values[0].replace('remove_', '')
        guild_id = str(interaction.guild.id)

        if guild_id in data['roles'] and identifier in data['roles'][guild_id]:
            role = self.guild.get_role(int(identifier))
            role_name = role.name if role else f"Роль {identifier}"
            data['roles'][guild_id].remove(identifier)

            if not data['roles'][guild_id]:
                del data['roles'][guild_id]

            save_data(data)
            await interaction.response.send_message(f"✅ Роль '{role_name}' убрана из подсчёта!", ephemeral=True)
            await log_to_channel(f"👤 Роль '{role_name}' убрана из подсчёта пользователем {interaction.user.name}")
            await log_action(interaction, "remove_role", detail=f"{role_name} ({identifier})")
        else:
            await interaction.response.send_message("⚠️ Роль не найдена!", ephemeral=True)

# ============ ВКЛЮЧЕНИЕ МП ============
class AddEventView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(AddEventSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await guard_interaction(interaction)

class AddEventSelect(discord.ui.Select):
    def __init__(self):
        enabled = set(data.get('enabled_events', []))
        options = []

        for name, times in EVENTS.items():
            if name in enabled:
                continue  # уже включён
            options.append(
                discord.SelectOption(
                    label=f"🗓️ {name}",
                    value=f"event_{name}",
                    description=", ".join(times)
                )
            )

        if not options:
            options.append(
                discord.SelectOption(label="✅ Все МП уже включены", value="none", default=True)
            )

        super().__init__(placeholder="Выберите МП...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("⚠️ Все МП уже включены!", ephemeral=True)
            return

        name = self.values[0].split('_', 1)[1]
        if name not in EVENTS:
            await interaction.response.send_message("❌ Неизвестное МП!", ephemeral=True)
            return

        enabled = data.setdefault('enabled_events', [])
        if name not in enabled:
            enabled.append(name)
            save_data(data)
            await interaction.response.send_message(
                f"✅ МП «{name}» включено в расписание ({', '.join(EVENTS[name])})!", ephemeral=True
            )
            await log_to_channel(f"🗓️ МП «{name}» включено пользователем {interaction.user.name}")
            await log_action(interaction, "enable_event", detail=name)
        else:
            await interaction.response.send_message("⚠️ Это МП уже включено!", ephemeral=True)

# ============ ИСКЛЮЧЕНИЕ МП ============
class RemoveEventView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(RemoveEventSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await guard_interaction(interaction)

class RemoveEventSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for name in data.get('enabled_events', []):
            options.append(
                discord.SelectOption(
                    label=f"🗓️ {name}",
                    value=f"remove_{name}",
                    description=", ".join(EVENTS.get(name, []))
                )
            )

        if not options:
            options.append(discord.SelectOption(label="Нет включённых МП", value="none", default=True))

        super().__init__(placeholder="Выберите МП для исключения...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("⚠️ Нет включённых МП!", ephemeral=True)
            return

        name = self.values[0].split('_', 1)[1]
        enabled = data.get('enabled_events', [])
        if name in enabled:
            enabled.remove(name)
            save_data(data)
            await interaction.response.send_message(f"✅ МП «{name}» исключено из расписания!", ephemeral=True)
            await log_to_channel(f"🗓️ МП «{name}» исключено пользователем {interaction.user.name}")
            await log_action(interaction, "disable_event", detail=name)
        else:
            await interaction.response.send_message("⚠️ Это МП не включено!", ephemeral=True)

# ============ ВЫБОР ДАТЫ ============
class DatePickerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        now = datetime.now(MSK)
        for i in range(7):
            date = now - timedelta(days=i)
            self.add_item(DateButton(date.strftime("%Y-%m-%d")))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await guard_interaction(interaction)

class DateButton(discord.ui.Button):
    def __init__(self, date_str):
        super().__init__(label=date_str, style=discord.ButtonStyle.secondary, custom_id=f"date_{date_str}")
        self.date_str = date_str

    async def callback(self, interaction: discord.Interaction):
        # Шаг 1: выбрана дата -> предлагаем выбрать время (только те, по которым есть снимки)
        guild_id = str(interaction.guild.id)
        day = data['history'].get(guild_id, {}).get(self.date_str, {})
        times = sorted(day.keys())

        if not times:
            await interaction.response.send_message(f"📭 Нет данных за {self.date_str}", ephemeral=True)
            return

        view = TimeSelectView(self.date_str, times)
        await interaction.response.send_message(
            f"📅 **{self.date_str}** — выберите время снимка:",
            view=view,
            ephemeral=True,
        )

# ============ ВЫБОР ВРЕМЕНИ ============
class TimeSelectView(discord.ui.View):
    def __init__(self, date_str, times):
        super().__init__(timeout=120)
        self.add_item(TimeSelect(date_str, times))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await guard_interaction(interaction)

class TimeSelect(discord.ui.Select):
    def __init__(self, date_str, times):
        self.date_str = date_str
        options = [
            discord.SelectOption(label=f"🕐 {t}", value=t)
            for t in times[:25]
        ]
        super().__init__(
            placeholder="Выберите время...",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        # Шаг 2: выбрано время -> показываем разбивку по ролям за этот снимок
        time_str = self.values[0]
        guild_id = str(interaction.guild.id)
        slot = data['history'].get(guild_id, {}).get(self.date_str, {}).get(time_str, {})

        embed = discord.Embed(
            title=f"📊 {self.date_str} в {time_str} (МСК)",
            color=discord.Color.green(),
        )

        if not slot:
            await interaction.response.send_message(
                f"📭 Нет данных за {self.date_str} {time_str}", ephemeral=True
            )
            return

        for channel_id, stats in slot.items():
            channel = interaction.guild.get_channel(int(channel_id))
            channel_name = channel.name if channel else channel_id
            total = stats.get('total', 0)
            roles = stats.get('roles', {})

            role_text = "\n".join(
                f"• {role}: {count} чел."
                for role, count in sorted(roles.items(), key=lambda x: x[1], reverse=True)
            )
            embed.add_field(
                name=f"🔊 {channel_name} — всего {total} чел.",
                value=role_text or "нет участников с ролями",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)
