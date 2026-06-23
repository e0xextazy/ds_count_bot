// Состояние бота (voice_data.json): загрузка, миграция, сохранение.
import fs from 'fs';
import { EVENTS } from './config.js';

export const DATA_FILE = process.env.DATA_FILE || 'voice_data.json';

function createDefaultData() {
  return {
    voice_channels: {},
    roles: {},
    settings: {},
    history: {},
    enabled_events: Object.keys(EVENTS),
  };
}

function migrateHistory(d) {
  // Переводит старый формат history[g][дата][channel_id]
  // в новый history[g][дата][время][channel_id].
  let changed = false;
  for (const dates of Object.values(d.history || {})) {
    for (const [date, entries] of Object.entries(dates)) {
      const oldChannelKeys = Object.keys(entries).filter((k) => !String(k).includes(':'));
      if (oldChannelKeys.length === 0) continue; // уже новый формат
      const newEntries = {};
      for (const [k, v] of Object.entries(entries)) {
        if (String(k).includes(':')) newEntries[k] = v;
      }
      for (const chId of oldChannelKeys) {
        const stats = entries[chId];
        const t = stats.timestamp || '00:00';
        newEntries[t] = newEntries[t] || {};
        newEntries[t][chId] = {
          total: stats.total || 0,
          roles: stats.roles || {},
          members: stats.members || [],
        };
      }
      dates[date] = newEntries;
      changed = true;
    }
  }
  return changed;
}

export function saveData(d) {
  fs.writeFileSync(DATA_FILE, JSON.stringify(d, null, 4), 'utf-8');
}

function loadData() {
  if (fs.existsSync(DATA_FILE)) {
    try {
      const d = JSON.parse(fs.readFileSync(DATA_FILE, 'utf-8'));
      const def = createDefaultData();
      let changed = false;
      for (const key of Object.keys(def)) {
        if (!(key in d)) {
          d[key] = def[key];
          changed = true;
          console.log(`🔄 Добавлен недостающий ключ: ${key}`);
        }
      }
      if (migrateHistory(d)) {
        changed = true;
        console.log('🔄 История переведена в формат с временем (дата → время → канал)');
      }
      if (changed) saveData(d);
      return d;
    } catch (e) {
      console.log(`⚠️ Ошибка загрузки данных: ${e.message}`);
      return createDefaultData();
    }
  }
  return createDefaultData();
}

// Единый объект состояния, разделяемый всеми модулями (мутируется на месте).
export const data = loadData();

export function getGuildRoleIds(guildId) {
  // Список ID ролей (строки) для подсчёта на конкретном сервере.
  return (data.roles[String(guildId)] || []).map(String);
}
