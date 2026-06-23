// Определение роли участника, подсчёт по ролям и расписание МП.
import { EVENTS } from './config.js';
import { data } from './storage.js';

export function getMemberRole(member, guild, roleIds) {
  // Если подходящих ролей несколько, выигрывает та, что выше в иерархии
  // сервера (наибольший position). Возвращает id роли (строку) или null.
  let best = null;
  for (const roleId of roleIds) {
    const role = guild.roles.cache.get(roleId);
    if (role && member.roles.cache.has(roleId)) {
      if (!best || role.position > best.position) best = role;
    }
  }
  return best ? best.id : null;
}

export function countMembersByRole(channel, guild, roleIds) {
  // Возвращает { roleCounts, total, members }, где members — список объектов
  // { id, name (ник), login (дискорд-логин), role (имя засчитанной роли или null) }
  // по КАЖДОМУ присутствующему не-боту.
  const roleCounts = {};
  let total = 0;
  const members = [];

  for (const member of channel.members.values()) {
    if (member.user.bot) continue;
    total += 1;

    const roleId = getMemberRole(member, guild, roleIds);
    let roleName = null;
    if (roleId) {
      const role = guild.roles.cache.get(roleId);
      roleName = role ? role.name : `Роль ${roleId}`;
      roleCounts[roleName] = (roleCounts[roleName] || 0) + 1;
    }

    members.push({
      id: member.id,
      name: member.displayName,
      login: member.user.username,
      role: roleName,
    });
  }

  return { roleCounts, total, members };
}

export function getEventAtTime(currentTime) {
  // Имя включённого МП, чьё время совпадает с currentTime, либо null.
  for (const name of data.enabled_events || []) {
    if ((EVENTS[name] || []).includes(currentTime)) return name;
  }
  return null;
}

export function getScheduleSummary() {
  const lines = [];
  for (const name of data.enabled_events || []) {
    const times = EVENTS[name] || [];
    if (times.length) lines.push(`**${name}** — ${times.join(', ')}`);
  }
  return lines.join('\n') || 'нет включённых МП';
}
