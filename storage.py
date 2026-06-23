"""Состояние бота (voice_data.json): загрузка, миграция, сохранение."""
import json
import os

from config import EVENTS

DATA_FILE = os.environ.get("DATA_FILE", "voice_data.json")


def create_default_data():
    return {
        'voice_channels': {},
        'roles': {},
        'settings': {},
        'history': {},
        'enabled_events': list(EVENTS.keys())
    }


def migrate_history(data):
    """Переводит старый формат истории history[g][дата][channel_id]
    в новый history[g][дата][время][channel_id]. Различаем уровни по наличию
    ':' в ключе: время = 'HH:MM', channel_id — числовая строка."""
    changed = False
    for gid, dates in data.get('history', {}).items():
        for date, entries in list(dates.items()):
            old_channel_keys = [k for k in entries if ':' not in str(k)]
            if not old_channel_keys:
                continue  # уже новый формат
            new_entries = {k: v for k, v in entries.items() if ':' in str(k)}
            for ch_id in old_channel_keys:
                stats = entries[ch_id]
                t = stats.get('timestamp', '00:00')
                new_entries.setdefault(t, {})[ch_id] = {
                    'total': stats.get('total', 0),
                    'roles': stats.get('roles', {}),
                    'members': stats.get('members', []),
                }
            dates[date] = new_entries
            changed = True
    return changed


def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            default_data = create_default_data()
            changed = False
            for key in default_data:
                if key not in data:
                    data[key] = default_data[key]
                    changed = True
                    print(f"🔄 Добавлен недостающий ключ: {key}")

            if migrate_history(data):
                changed = True
                print("🔄 История переведена в формат с временем (дата → время → канал)")

            if changed:
                save_data(data)
            return data
        except Exception as e:
            print(f"⚠️ Ошибка загрузки данных: {e}")
            return create_default_data()
    return create_default_data()


def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# Единый объект состояния, разделяемый всеми модулями (мутируется на месте).
data = load_data()


def get_guild_role_ids(guild_id):
    """Список ID ролей (int) для подсчёта на конкретном сервере.
    Берётся из data['roles'][guild_id]; по умолчанию пуст."""
    return [int(rid) for rid in data['roles'].get(str(guild_id), [])]
