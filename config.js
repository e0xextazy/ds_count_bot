// Конфигурация из окружения, каталог МП и проверка доступа.
import 'dotenv/config';
import { DateTime } from 'luxon';
import { PermissionFlagsBits } from 'discord.js';

// Московское время (UTC+3) для всех меток времени и расписания
export const MSK = 'Europe/Moscow';

export function mskNow() {
  return DateTime.now().setZone(MSK);
}

// ============ КОНФИГУРАЦИЯ ============
// Значения читаются из переменных окружения (см. .env / docker-compose.yml).
export const TOKEN = process.env.DISCORD_TOKEN || '';
export const LOG_CHANNEL_ID = process.env.LOG_CHANNEL_ID || '';   // '' — логи в канал выключены
export const TEST_GUILD_ID = process.env.TEST_GUILD_ID || '';     // сервер для синхронизации слэш-команд

function parseUserIds(raw) {
  const ids = new Set();
  for (const part of (raw || '').replace(/;/g, ',').split(',')) {
    const p = part.trim();
    if (/^\d+$/.test(p)) ids.add(p);
  }
  return ids;
}

// Доступ к боту: администраторы Discord + явно перечисленные пользователи (whitelist).
export const ALLOWED_USER_IDS = parseUserIds(process.env.ALLOWED_USER_IDS || '');

function parseBool(raw) {
  return ['1', 'true', 'yes', 'on'].includes(String(raw).trim().toLowerCase());
}

// Экспорт результатов пересчёта в Google Sheets. По умолчанию выключен.
export const EXPORT_TO_SHEET = parseBool(process.env.EXPORT2SHEET || 'false');

export function isAllowed(member) {
  // member — GuildMember (из interaction.member / message.member)
  if (!member) return false;
  const userId = member.user ? member.user.id : member.id;
  if (ALLOWED_USER_IDS.has(String(userId))) return true;
  try {
    return member.permissions?.has(PermissionFlagsBits.Administrator) ?? false;
  } catch {
    return false;
  }
}

// ============ КАТАЛОГ МП (МЕРОПРИЯТИЙ) ============
// Захардкоженный список мероприятий и их времени (МСК).
// Кнопками «Добавить МП» / «Убрать МП» включаются/выключаются МП,
// участвующие в запланированном пересчёте (data.enabled_events).
export const EVENTS = {
  'Диллеры': ['10:55', '18:55'],
  'Цеха': ['14:55', '22:55'],
  'Дроп': ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'],
};
