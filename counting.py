"""Определение роли участника, подсчёт по ролям и расписание МП."""
from config import EVENTS
from storage import data


def get_member_role(member, guild, role_ids):
    """
    Определяет роль участника из переданного списка role_ids.
    Если подходящих ролей несколько, выигрывает та, что выше в иерархии
    сервера (наибольший position). Возвращает None, если ни одной роли
    из списка у участника нет.
    """
    best_role = None
    for role_id in role_ids:
        role = guild.get_role(role_id)
        if role and role in member.roles:
            if best_role is None or role.position > best_role.position:
                best_role = role
    return best_role.id if best_role else None


def count_members_by_role(channel, guild, role_ids):
    """
    Подсчет участников в канале по ролям из списка role_ids.

    Возвращает (role_counts, total_members, members):
      • role_counts — {имя роли: количество} (только по ролям из списка);
      • total_members — все не-боты в войсе;
      • members — список словарей по КАЖДОМУ присутствующему не-боту:
        {id, name (ник), login (дискорд-логин), role (имя засчитанной роли или None)}.
    """
    role_counts = {}
    total_members = 0
    members = []

    for member in channel.members:
        if member.bot:
            continue

        total_members += 1

        # Получаем роль участника по нашему фильтру (None — роли из списка нет)
        role_id = get_member_role(member, guild, role_ids)
        role_name = None
        if role_id is not None:
            role = guild.get_role(role_id)
            role_name = role.name if role else f"Роль {role_id}"
            role_counts[role_name] = role_counts.get(role_name, 0) + 1

        members.append({
            'id': str(member.id),
            'name': member.display_name,
            'login': member.name,
            'role': role_name,
        })

    return role_counts, total_members, members


def get_event_at_time(current_time):
    """Возвращает имя включённого МП, у которого время совпадает с current_time,
    либо None. Времена МП не пересекаются, поэтому совпадение однозначно."""
    for name in data.get('enabled_events', []):
        if current_time in EVENTS.get(name, []):
            return name
    return None


def get_schedule_summary():
    """Текст со включёнными МП и их временем для админ-панели."""
    lines = []
    for name in data.get('enabled_events', []):
        times = EVENTS.get(name, [])
        if times:
            lines.append(f"**{name}** — {', '.join(times)}")
    return "\n".join(lines) or "нет включённых МП"
