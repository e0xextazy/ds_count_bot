// Экземпляр клиента Discord (intents) и помощники логирования.
import { Client, GatewayIntentBits } from 'discord.js';
import { LOG_CHANNEL_ID } from './config.js';
import * as db from './db.js';

export const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.GuildVoiceStates,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
  ],
});

export async function logToChannel(message, embed = null) {
  if (!LOG_CHANNEL_ID) return;
  try {
    const channel = await client.channels.fetch(LOG_CHANNEL_ID).catch(() => null);
    if (!channel) return;
    if (embed) await channel.send({ embeds: [embed] });
    else await channel.send(`[LOG] ${message}`);
  } catch (e) {
    console.log(`⚠️ Не удалось отправить лог в канал: ${e.message}`);
  }
}

export async function logAction(interaction, eventType, detail = null) {
  // Семантическая запись действия пользователя в event_logs.
  await db.logEvent({
    event_type: eventType,
    guild_id: interaction.guildId ?? null,
    channel_id: interaction.channelId ?? null,
    user_id: interaction.user ? interaction.user.id : null,
    user_name: interaction.user ? interaction.user.tag : null,
    detail,
  });
}
