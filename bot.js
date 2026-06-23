// Точка входа: события, команды, инициализация и запуск бота.
//
// Логика разнесена по модулям:
//   config   — константы, каталог МП, доступ;
//   storage  — состояние (voice_data.json);
//   client   — экземпляр клиента и логирование;
//   counting — подсчёт по ролям и расписание МП;
//   recalc   — пересчёт и фоновая задача;
//   views    — кнопки/селекты админ-панели.
import { Events, REST, Routes, InteractionType } from 'discord.js';
import { TOKEN, TEST_GUILD_ID, isAllowed } from './config.js';
import { data } from './storage.js';
import { client, logToChannel } from './client.js';
import { buildAdminPanel, handleComponent } from './views.js';
import { startScheduler } from './recalc.js';
import * as db from './db.js';

const COMMANDS = [{ name: 'admin_panel', description: 'Открыть админ-панель управления' }];

// ============ СОБЫТИЯ ============
client.once(Events.ClientReady, async (c) => {
  console.log(`✅ Бот ${c.user.tag} запущен!`);
  console.log(`📊 На серверах: ${c.guilds.cache.size}`);
  for (const guild of c.guilds.cache.values()) {
    console.log(`  - Сервер: ${guild.name} (ID: ${guild.id})`);
  }

  try {
    const rest = new REST({ version: '10' }).setToken(TOKEN);
    if (TEST_GUILD_ID) {
      await rest.put(Routes.applicationGuildCommands(c.user.id, TEST_GUILD_ID), { body: COMMANDS });
      console.log('✅ Синхронизированы слэш-команды для сервера');
    } else {
      await rest.put(Routes.applicationCommands(c.user.id), { body: COMMANDS });
      console.log('✅ Синхронизированы глобальные слэш-команды');
    }
  } catch (e) {
    console.log(`❌ Ошибка синхронизации: ${e.message}`);
  }

  startScheduler();

  const totalVoice = Object.values(data.voice_channels).reduce((acc, ch) => acc + ch.length, 0);
  await logToChannel(`🤖 Бот запущен! Отслеживается ${totalVoice} каналов.`);
  console.log('✅ Бот полностью готов к работе!');
});

client.on(Events.InteractionCreate, async (interaction) => {
  // Централизованное логирование ВСЕХ интеракций
  try {
    let eventType = 'interaction';
    let detail = '';
    if (interaction.isChatInputCommand()) {
      eventType = 'slash_command';
      detail = `/${interaction.commandName}`;
    } else if (interaction.isButton() || interaction.isStringSelectMenu()) {
      eventType = 'component';
      detail = interaction.customId;
    } else if (interaction.type === InteractionType.ModalSubmit) {
      eventType = 'modal_submit';
      detail = interaction.customId;
    }
    await db.logEvent({
      event_type: eventType,
      guild_id: interaction.guildId,
      channel_id: interaction.channelId,
      user_id: interaction.user ? interaction.user.id : null,
      user_name: interaction.user ? interaction.user.tag : null,
      detail,
    });
  } catch (e) {
    console.log(`⚠️ Ошибка логирования интеракции: ${e.message}`);
  }

  // Контроль доступа
  if (!isAllowed(interaction.member)) {
    if (interaction.isRepliable()) {
      await interaction.reply({ content: '⛔ У тебя нет доступа.', ephemeral: true }).catch(() => {});
    }
    return;
  }

  try {
    if (interaction.isChatInputCommand() && interaction.commandName === 'admin_panel') {
      await interaction.reply({ ...buildAdminPanel(), ephemeral: true });
    } else if (interaction.isButton() || interaction.isStringSelectMenu()) {
      await handleComponent(interaction);
    }
  } catch (e) {
    console.log(`❌ Ошибка обработки интеракции: ${e.message}`);
  }
});

client.on(Events.MessageCreate, async (message) => {
  if (message.author.bot || !message.content.startsWith('!')) return;
  const cmd = message.content.slice(1).trim().split(/\s+/)[0].toLowerCase();
  if (!['admin', 'panel', 'sync'].includes(cmd)) return;

  await db.logEvent({
    event_type: 'text_command',
    guild_id: message.guildId,
    channel_id: message.channelId,
    user_id: message.author.id,
    user_name: message.author.tag,
    detail: `!${cmd}`,
  });

  if (cmd === 'sync') {
    const app = await client.application.fetch();
    const ownerId = app.owner?.id;
    if (message.author.id !== ownerId) return;
    try {
      const rest = new REST({ version: '10' }).setToken(TOKEN);
      if (TEST_GUILD_ID) {
        await rest.put(Routes.applicationGuildCommands(client.user.id, TEST_GUILD_ID), { body: COMMANDS });
        await message.reply('✅ Синхронизировано команд для сервера');
      } else {
        await rest.put(Routes.applicationCommands(client.user.id), { body: COMMANDS });
        await message.reply('✅ Синхронизировано глобальных команд');
      }
    } catch (e) {
      await message.reply(`❌ Ошибка: ${e.message}`);
    }
    return;
  }

  // admin / panel
  if (!isAllowed(message.member)) return;
  await message.reply(buildAdminPanel());
});

client.on(Events.Error, (err) => {
  console.log(`❌ Ошибка клиента: ${err.message}`);
});

// ============ ЗАПУСК ============
if (!TOKEN) {
  console.log('='.repeat(50));
  console.log('❌ ОШИБКА: Не указан токен бота!');
  console.log('Задайте переменную окружения DISCORD_TOKEN (см. .env / docker-compose.yml)');
  console.log('='.repeat(50));
  process.exit(1);
}

console.log('='.repeat(50));
console.log('🚀 ЗАПУСК БОТА (JS)');
console.log('='.repeat(50));

await db.initDb();
client.login(TOKEN).catch((e) => {
  console.log(`❌ Ошибка входа: ${e.message}`);
  process.exit(1);
});
