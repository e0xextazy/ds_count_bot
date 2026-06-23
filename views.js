// Компоненты админ-панели (кнопки/селекты) и маршрутизация интеракций.
import {
  ActionRowBuilder, ButtonBuilder, ButtonStyle,
  StringSelectMenuBuilder, EmbedBuilder, ChannelType,
} from 'discord.js';
import { EVENTS, mskNow } from './config.js';
import { data, saveData } from './storage.js';
import { logToChannel, logAction } from './client.js';
import { getScheduleSummary } from './counting.js';
import { performFullRecalc } from './recalc.js';

const VOICE_TYPES = [ChannelType.GuildVoice, ChannelType.GuildStageVoice];
const cut = (s) => String(s).slice(0, 100);

// ============ ПАНЕЛЬ ============
export function buildAdminPanel() {
  const embed = new EmbedBuilder()
    .setTitle('⚙️ Админ панель')
    .setDescription('Управление голосовыми и сценическими каналами')
    .setColor(0x3498db)
    .addFields({ name: '⏰ Запланированные пересчёты (МП)', value: getScheduleSummary(), inline: false });

  const rows = [
    new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId('start_recalc').setLabel('📊 Пересчет всех').setStyle(ButtonStyle.Primary)),
    new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId('add_voice').setLabel('🔊 Добавить войс').setStyle(ButtonStyle.Success),
      new ButtonBuilder().setCustomId('remove_voice').setLabel('🔇 Убрать войс').setStyle(ButtonStyle.Danger)),
    new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId('add_role').setLabel('👤 Добавить роль').setStyle(ButtonStyle.Success),
      new ButtonBuilder().setCustomId('remove_role').setLabel('👤 Убрать роль').setStyle(ButtonStyle.Danger)),
    new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId('add_event').setLabel('🗓️ Добавить МП').setStyle(ButtonStyle.Success),
      new ButtonBuilder().setCustomId('remove_event').setLabel('🗓️ Убрать МП').setStyle(ButtonStyle.Danger)),
    new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId('select_date').setLabel('📅 Выбрать дату').setStyle(ButtonStyle.Secondary),
      new ButtonBuilder().setCustomId('show_history').setLabel('📈 История').setStyle(ButtonStyle.Secondary)),
  ];
  return { embeds: [embed], components: rows };
}

function selectRow(customId, placeholder, options) {
  if (options.length === 0) options = [{ label: 'нет вариантов', value: 'none' }];
  const menu = new StringSelectMenuBuilder()
    .setCustomId(customId)
    .setPlaceholder(cut(placeholder))
    .addOptions(options.slice(0, 25));
  return new ActionRowBuilder().addComponents(menu);
}

// ============ БИЛДЕРЫ ПОДМЕНЮ ============
function buildAddChannelMenu(guild) {
  const options = [];
  for (const ch of guild.channels.cache.values()) {
    if (!VOICE_TYPES.includes(ch.type)) continue;
    const cat = ch.parent ? ch.parent.name : 'Без категории';
    const icon = ch.type === ChannelType.GuildStageVoice ? '🎤' : '🔊';
    options.push({ label: cut(`${icon} ${ch.name} [${cat}]`), value: ch.id, description: cut(`👥 ${ch.members.size} чел.`) });
  }
  return selectRow('sel_add_voice', 'Выберите голосовой или сценический канал...', options);
}

function buildRemoveChannelMenu(guild) {
  const options = [];
  for (const id of data.voice_channels[guild.id] || []) {
    const ch = guild.channels.cache.get(id);
    if (!ch) continue;
    const icon = ch.type === ChannelType.GuildStageVoice ? '🎤 Сценический' : '🔊 Голосовой';
    const cat = ch.parent ? ch.parent.name : 'Без категории';
    options.push({ label: cut(`${icon} ${ch.name}`), value: id, description: cut(cat) });
  }
  return selectRow('sel_remove_voice', 'Выберите войс, который убрать из отслеживания...', options);
}

function buildAddRoleMenu(guild) {
  const already = new Set((data.roles[guild.id] || []).map(String));
  const roles = [...guild.roles.cache.values()]
    .filter((r) => r.id !== guild.id && !r.managed && !already.has(r.id))
    .sort((a, b) => b.position - a.position);
  const options = roles.map((r) => ({ label: cut(`👤 ${r.name}`), value: r.id, description: cut(`👥 ${r.members.size} чел.`) }));
  return selectRow('sel_add_role', 'Выберите роль...', options);
}

function buildRemoveRoleMenu(guild) {
  const options = [];
  for (const id of data.roles[guild.id] || []) {
    const role = guild.roles.cache.get(id);
    const label = role ? role.name : `Роль ${id}`;
    options.push({ label: cut(`👤 ${label}`), value: id, description: role ? cut(`👥 ${role.members.size} чел.`) : 'роль не найдена на сервере' });
  }
  return selectRow('sel_remove_role', 'Выберите роль, которую убрать из подсчёта...', options);
}

function buildAddEventMenu() {
  const enabled = new Set(data.enabled_events || []);
  const options = Object.entries(EVENTS)
    .filter(([name]) => !enabled.has(name))
    .map(([name, times]) => ({ label: cut(`🗓️ ${name}`), value: name, description: cut(times.join(', ')) }));
  return selectRow('sel_add_event', 'Выберите МП...', options);
}

function buildRemoveEventMenu() {
  const options = (data.enabled_events || []).map((name) => ({ label: cut(`🗓️ ${name}`), value: name, description: cut((EVENTS[name] || []).join(', ')) }));
  return selectRow('sel_remove_event', 'Выберите МП для исключения...', options);
}

function buildDatePicker() {
  const now = mskNow();
  const rows = [];
  let row = new ActionRowBuilder();
  for (let i = 0; i < 7; i++) {
    const ds = now.minus({ days: i }).toFormat('yyyy-MM-dd');
    if (row.components.length === 5) { rows.push(row); row = new ActionRowBuilder(); }
    row.addComponents(new ButtonBuilder().setCustomId(`date:${ds}`).setLabel(ds).setStyle(ButtonStyle.Secondary));
  }
  if (row.components.length) rows.push(row);
  return rows;
}

function buildTimeSelect(dateStr, times) {
  const options = times.slice(0, 25).map((t) => ({ label: `🕐 ${t}`, value: t }));
  return selectRow(`sel_time:${dateStr}`, 'Выберите время...', options);
}

// ============ ОБРАБОТЧИКИ ============
async function onRecalc(interaction) {
  await interaction.deferReply({ ephemeral: true });
  const gid = interaction.guildId;
  const has = data.voice_channels[gid] && data.voice_channels[gid].length;
  if (has) {
    await logAction(interaction, 'recalc_manual');
    await performFullRecalc(gid, interaction);
    await interaction.editReply('✅ Полный пересчет выполнен! Результаты отправлены в этот канал.');
  } else {
    await interaction.editReply('⚠️ Нет настроенных каналов!');
  }
}

async function onHistory(interaction) {
  const gid = interaction.guildId;
  const embed = new EmbedBuilder().setTitle('📈 История проверок').setColor(0xf1c40f);
  const hist = data.history[gid];
  if (hist && Object.keys(hist).length) {
    const items = Object.entries(hist).slice(-5);
    for (const [dateStr, results] of items) {
      const times = Object.keys(results).sort().join(', ') || '—';
      embed.addFields({ name: `📅 ${dateStr}`, value: `Снимков: ${Object.keys(results).length} (${times})`, inline: false });
    }
    await interaction.reply({ embeds: [embed], ephemeral: true });
  } else {
    await interaction.reply({ content: '📭 История пуста!', ephemeral: true });
  }
}

async function onAddVoice(interaction) {
  const val = interaction.values[0];
  if (val === 'none') return interaction.update({ content: '⚠️ Нет доступных каналов!', components: [] });
  const gid = interaction.guildId;
  const channel = interaction.guild.channels.cache.get(val);
  if (!channel) return interaction.update({ content: '❌ Канал не найден!', components: [] });
  if (!VOICE_TYPES.includes(channel.type)) return interaction.update({ content: '❌ Это не голосовой и не сценический канал!', components: [] });

  data.voice_channels[gid] = data.voice_channels[gid] || [];
  if (!data.voice_channels[gid].includes(val)) {
    data.voice_channels[gid].push(val);
    saveData(data);
    const typeName = channel.type === ChannelType.GuildStageVoice ? 'Сценический' : 'Голосовой';
    await interaction.update({ content: `✅ ${typeName} канал '${channel.name}' добавлен!`, components: [] });
    await logToChannel(`🔊 Добавлен канал '${channel.name}' (${val}) пользователем ${interaction.user.username}`);
    await logAction(interaction, 'add_voice', `${channel.name} (${val})`);
  } else {
    await interaction.update({ content: '⚠️ Этот канал уже добавлен!', components: [] });
  }
}

async function onRemoveVoice(interaction) {
  const val = interaction.values[0];
  if (val === 'none') return interaction.update({ content: '⚠️ Нет войсов для удаления из отслеживания!', components: [] });
  const gid = interaction.guildId;
  const list = data.voice_channels[gid] || [];
  if (list.includes(val)) {
    const channel = interaction.guild.channels.cache.get(val);
    data.voice_channels[gid] = list.filter((x) => x !== val);
    if (!data.voice_channels[gid].length) delete data.voice_channels[gid];
    saveData(data);
    await interaction.update({ content: '✅ Войс убран из отслеживания!', components: [] });
    await logToChannel(`🔇 Войс убран из отслеживания пользователем ${interaction.user.username}`);
    await logAction(interaction, 'remove_voice', `${channel ? channel.name : '?'} (${val})`);
  } else {
    await interaction.update({ content: '⚠️ Канал не найден!', components: [] });
  }
}

async function onAddRole(interaction) {
  const val = interaction.values[0];
  if (val === 'none') return interaction.update({ content: '⚠️ Нет доступных ролей!', components: [] });
  const gid = interaction.guildId;
  const role = interaction.guild.roles.cache.get(val);
  if (!role) return interaction.update({ content: '❌ Роль не найдена!', components: [] });

  data.roles[gid] = data.roles[gid] || [];
  if (!data.roles[gid].includes(val)) {
    data.roles[gid].push(val);
    saveData(data);
    await interaction.update({ content: `✅ Роль '${role.name}' добавлена в подсчёт!`, components: [] });
    await logToChannel(`👤 Добавлена роль '${role.name}' (${val}) пользователем ${interaction.user.username}`);
    await logAction(interaction, 'add_role', `${role.name} (${val})`);
  } else {
    await interaction.update({ content: '⚠️ Эта роль уже добавлена!', components: [] });
  }
}

async function onRemoveRole(interaction) {
  const val = interaction.values[0];
  if (val === 'none') return interaction.update({ content: '⚠️ Нет ролей для удаления из подсчёта!', components: [] });
  const gid = interaction.guildId;
  const list = data.roles[gid] || [];
  if (list.includes(val)) {
    const role = interaction.guild.roles.cache.get(val);
    const roleName = role ? role.name : `Роль ${val}`;
    data.roles[gid] = list.filter((x) => x !== val);
    if (!data.roles[gid].length) delete data.roles[gid];
    saveData(data);
    await interaction.update({ content: `✅ Роль '${roleName}' убрана из подсчёта!`, components: [] });
    await logToChannel(`👤 Роль '${roleName}' убрана из подсчёта пользователем ${interaction.user.username}`);
    await logAction(interaction, 'remove_role', `${roleName} (${val})`);
  } else {
    await interaction.update({ content: '⚠️ Роль не найдена!', components: [] });
  }
}

async function onAddEvent(interaction) {
  const name = interaction.values[0];
  if (name === 'none') return interaction.update({ content: '⚠️ Все МП уже включены!', components: [] });
  if (!(name in EVENTS)) return interaction.update({ content: '❌ Неизвестное МП!', components: [] });

  data.enabled_events = data.enabled_events || [];
  if (!data.enabled_events.includes(name)) {
    data.enabled_events.push(name);
    saveData(data);
    await interaction.update({ content: `✅ МП «${name}» включено в расписание (${EVENTS[name].join(', ')})!`, components: [] });
    await logToChannel(`🗓️ МП «${name}» включено пользователем ${interaction.user.username}`);
    await logAction(interaction, 'enable_event', name);
  } else {
    await interaction.update({ content: '⚠️ Это МП уже включено!', components: [] });
  }
}

async function onRemoveEvent(interaction) {
  const name = interaction.values[0];
  if (name === 'none') return interaction.update({ content: '⚠️ Нет включённых МП!', components: [] });
  const enabled = data.enabled_events || [];
  if (enabled.includes(name)) {
    data.enabled_events = enabled.filter((x) => x !== name);
    saveData(data);
    await interaction.update({ content: `✅ МП «${name}» исключено из расписания!`, components: [] });
    await logToChannel(`🗓️ МП «${name}» исключено пользователем ${interaction.user.username}`);
    await logAction(interaction, 'disable_event', name);
  } else {
    await interaction.update({ content: '⚠️ Это МП не включено!', components: [] });
  }
}

async function onDatePicked(interaction, dateStr) {
  const gid = interaction.guildId;
  const day = (data.history[gid] || {})[dateStr] || {};
  const times = Object.keys(day).sort();
  if (!times.length) return interaction.update({ content: `📭 Нет данных за ${dateStr}`, components: [] });
  await interaction.update({ content: `📅 **${dateStr}** — выберите время снимка:`, components: [buildTimeSelect(dateStr, times)] });
}

async function onTimePicked(interaction, dateStr) {
  const timeStr = interaction.values[0];
  const gid = interaction.guildId;
  const slot = (((data.history[gid] || {})[dateStr]) || {})[timeStr] || {};
  if (!Object.keys(slot).length) return interaction.update({ content: `📭 Нет данных за ${dateStr} ${timeStr}`, components: [] });

  const embed = new EmbedBuilder().setTitle(`📊 ${dateStr} в ${timeStr} (МСК)`).setColor(0x2ecc71);
  for (const [channelId, stats] of Object.entries(slot)) {
    const channel = interaction.guild.channels.cache.get(channelId);
    const channelName = channel ? channel.name : channelId;
    const total = stats.total || 0;
    const roles = stats.roles || {};
    const roleText = Object.entries(roles).sort((a, b) => b[1] - a[1]).map(([r, c]) => `• ${r}: ${c} чел.`).join('\n');
    embed.addFields({ name: `🔊 ${channelName} — всего ${total} чел.`, value: roleText || 'нет участников с ролями', inline: false });
  }
  await interaction.update({ content: '', embeds: [embed], components: [] });
}

// ============ МАРШРУТИЗАЦИЯ ============
export async function handleComponent(interaction) {
  const id = interaction.customId;

  if (interaction.isButton()) {
    switch (id) {
      case 'start_recalc': return onRecalc(interaction);
      case 'add_voice': return interaction.reply({ content: 'Выберите голосовой или сценический канал:', components: [buildAddChannelMenu(interaction.guild)], ephemeral: true });
      case 'remove_voice': return interaction.reply({ content: 'Выберите войс, который убрать из отслеживания:', components: [buildRemoveChannelMenu(interaction.guild)], ephemeral: true });
      case 'add_role': return interaction.reply({ content: 'Выберите роль для подсчёта:', components: [buildAddRoleMenu(interaction.guild)], ephemeral: true });
      case 'remove_role': return interaction.reply({ content: 'Выберите роль, которую убрать из подсчёта:', components: [buildRemoveRoleMenu(interaction.guild)], ephemeral: true });
      case 'add_event': return interaction.reply({ content: 'Выберите МП для включения в расписание:', components: [buildAddEventMenu()], ephemeral: true });
      case 'remove_event': return interaction.reply({ content: 'Выберите МП для исключения из расписания:', components: [buildRemoveEventMenu()], ephemeral: true });
      case 'select_date': return interaction.reply({ content: 'Выберите дату для просмотра результатов:', components: buildDatePicker(), ephemeral: true });
      case 'show_history': return onHistory(interaction);
      default:
        if (id.startsWith('date:')) return onDatePicked(interaction, id.slice(5));
    }
  } else if (interaction.isStringSelectMenu()) {
    switch (id) {
      case 'sel_add_voice': return onAddVoice(interaction);
      case 'sel_remove_voice': return onRemoveVoice(interaction);
      case 'sel_add_role': return onAddRole(interaction);
      case 'sel_remove_role': return onRemoveRole(interaction);
      case 'sel_add_event': return onAddEvent(interaction);
      case 'sel_remove_event': return onRemoveEvent(interaction);
      default:
        if (id.startsWith('sel_time:')) return onTimePicked(interaction, id.slice('sel_time:'.length));
    }
  }
}
