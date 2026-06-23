// Полный пересчёт войсов и фоновая задача по расписанию МП.
import { ChannelType, PermissionFlagsBits, EmbedBuilder } from 'discord.js';
import { MSK, mskNow, EXPORT_TO_SHEET } from './config.js';
import { client, logToChannel } from './client.js';
import { data, saveData, getGuildRoleIds } from './storage.js';
import { countMembersByRole, getEventAtTime } from './counting.js';
import * as db from './db.js';
import * as sheets from './sheets.js';

const VOICE_TYPES = [ChannelType.GuildVoice, ChannelType.GuildStageVoice];

export async function performFullRecalc(guildId, interaction = null, eventName = null) {
  try {
    const trigger = interaction ? 'manual' : 'scheduled';
    const guild = client.guilds.cache.get(String(guildId));
    if (!guild) {
      console.log(`❌ Сервер ${guildId} не найден`);
      return;
    }

    const now = mskNow();
    const today = now.toFormat('yyyy-MM-dd');
    const currentTime = now.toFormat('HH:mm');

    let targetChannel = null;
    if (interaction && interaction.channel) {
      targetChannel = interaction.channel;
    } else {
      const me = guild.members.me;
      targetChannel = guild.channels.cache.find((ch) => ch.type === ChannelType.GuildText
        && ch.permissionsFor(me)?.has(PermissionFlagsBits.SendMessages)
        && ch.permissionsFor(me)?.has(PermissionFlagsBits.ViewChannel));
    }
    if (!targetChannel) {
      console.log(`⚠️ Нет доступных каналов на сервере ${guild.name}`);
      return;
    }

    const triggeredBy = (interaction && interaction.user)
      ? `Выполнил: ${interaction.member?.displayName || interaction.user.username}`
      : '⏰ Плановый пересчёт по расписанию';

    // Пересчитываем ВСЕ голосовые/сценические каналы с подключёнными людьми.
    const connected = [...guild.channels.cache.values()]
      .filter((ch) => VOICE_TYPES.includes(ch.type) && ch.members.size > 0);

    // Структура истории: history[guild][дата][время][channel_id] = {...}
    data.history[String(guildId)] = data.history[String(guildId)] || {};
    data.history[String(guildId)][today] = data.history[String(guildId)][today] || {};
    const timeSlot = data.history[String(guildId)][today][currentTime] = data.history[String(guildId)][today][currentTime] || {};

    let bestTotal = -1;
    let bestRoles = {};
    let bestChannel = null;

    const roleIds = getGuildRoleIds(guildId);

    for (const channel of connected) {
      const { roleCounts, total, members } = countMembersByRole(channel, guild, roleIds);

      const membersInfo = members.filter((m) => m.role).map((m) => `${m.name} (${m.role})`);
      timeSlot[channel.id] = { total, roles: roleCounts, members: membersInfo.slice(0, 20) };

      // count_logs: агрегированный результат по этому войсу
      await db.logCount({
        guild_id: guildId, channel_id: channel.id, channel_name: channel.name,
        event_name: eventName, trigger, total, roles: roleCounts,
      });

      // members_logs: поимённый состав войса
      await db.logMembers(members.map((m) => ({
        guild_id: guildId, channel_id: channel.id, channel_name: channel.name,
        event_name: eventName, trigger,
        member_id: m.id, member_name: m.name, member_login: m.login, role_name: m.role,
      })));

      if (total > bestTotal) {
        bestTotal = total;
        bestRoles = roleCounts;
        bestChannel = channel;
      }
    }

    // В DC-канал отправляем карточку только по войсу-победителю
    if (bestChannel) {
      const isStage = bestChannel.type === ChannelType.GuildStageVoice;
      const icon = isStage ? '🎤' : '🔊';
      const embed = new EmbedBuilder()
        .setTitle(`${icon} ${bestChannel.name}`)
        .setDescription(`📅 ${now.toFormat('dd.MM.yyyy HH:mm')}`)
        .setColor(isStage ? 0x9b59b6 : 0x3498db)
        .addFields({ name: '👥 Всего учтено', value: `**${bestTotal}** человек`, inline: false });

      const sortedRoles = Object.entries(bestRoles).sort((a, b) => b[1] - a[1]);
      for (const [roleName, count] of sortedRoles) {
        embed.addFields({ name: `👤 ${roleName}`, value: `${count} чел.`, inline: true });
      }
      embed.setFooter({ text: triggeredBy });
      await targetChannel.send({ embeds: [embed] });
    } else {
      await targetChannel.send('ℹ️ Ни в одном голосовом канале нет подключённых участников.');
    }

    // Экспорт в Google Sheets — только в 10:55 и 18:55 и при включённом флаге.
    if (EXPORT_TO_SHEET && sheets.EVENT_TIMES.includes(currentTime)) {
      const sheetDate = now.toFormat('dd.MM');
      try {
        const result = await sheets.updateEvent(sheetDate, currentTime, bestRoles);
        if (result) {
          await logToChannel(`📗 Google Sheets обновлён (войс «${bestChannel ? bestChannel.name : '—'}», ${Math.max(bestTotal, 0)} чел.): ${result}`);
        }
      } catch (e) {
        console.log(`⚠️ Ошибка экспорта в Google Sheets: ${e.message}`);
        await logToChannel(`⚠️ Ошибка экспорта в Google Sheets: ${e.message}`);
      }
    }

    saveData(data);
  } catch (e) {
    const msg = `Ошибка при пересчете: ${e.message}`;
    console.log(`❌ ${msg}`);
    await logToChannel(`❌ ${msg}`);
  }
}

// ============ ФОНОВАЯ ЗАДАЧА ============
let _lastFiredMinute = null;

export function startScheduler() {
  // Проверяем раз в 30с; дедуп по минуте, чтобы не сработать дважды за минуту.
  setInterval(async () => {
    const now = mskNow();
    const currentTime = now.toFormat('HH:mm');
    if (currentTime === _lastFiredMinute) return;

    const eventName = getEventAtTime(currentTime);
    if (eventName) {
      _lastFiredMinute = currentTime;
      await logToChannel(`⏰ Запланированный пересчёт «${eventName}» в ${currentTime}`);
      for (const guildId of Object.keys(data.voice_channels)) {
        await performFullRecalc(guildId, null, eventName);
      }
    }
  }, 30_000);
  console.log('✅ Запланированные пересчёты активны!');
}
