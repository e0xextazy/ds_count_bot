// Логирование работы бота в PostgreSQL (pg).
//
// Три таблицы:
//   • event_logs   — любое действие с ботом (кнопки, селекты, команды);
//   • count_logs   — результат каждого пересчёта по каждому войсу;
//   • members_logs — поимённый состав участников на момент пересчёта.
import pg from 'pg';

const DATABASE_URL = process.env.DATABASE_URL || '';

let pool = null;

export async function initDb() {
  if (!DATABASE_URL) {
    console.log('ℹ️  DATABASE_URL не задан — логирование в PostgreSQL отключено.');
    return null;
  }

  pool = new pg.Pool({ connectionString: DATABASE_URL, max: 5 });

  await pool.query(`
    CREATE TABLE IF NOT EXISTS event_logs (
      id          BIGSERIAL PRIMARY KEY,
      event_type  TEXT        NOT NULL,
      guild_id    TEXT,
      channel_id  TEXT,
      user_id     TEXT,
      user_name   TEXT,
      detail      TEXT,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )`);
  await pool.query('CREATE INDEX IF NOT EXISTS idx_event_logs_created_at ON event_logs (created_at)');
  await pool.query('CREATE INDEX IF NOT EXISTS idx_event_logs_type ON event_logs (event_type)');

  await pool.query(`
    CREATE TABLE IF NOT EXISTS count_logs (
      id            BIGSERIAL PRIMARY KEY,
      guild_id      TEXT,
      channel_id    TEXT,
      channel_name  TEXT,
      event_name    TEXT,
      trigger       TEXT,
      total         INTEGER     NOT NULL DEFAULT 0,
      roles         JSONB,
      created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
    )`);
  await pool.query('CREATE INDEX IF NOT EXISTS idx_count_logs_created_at ON count_logs (created_at)');

  await pool.query(`
    CREATE TABLE IF NOT EXISTS members_logs (
      id            BIGSERIAL PRIMARY KEY,
      guild_id      TEXT,
      channel_id    TEXT,
      channel_name  TEXT,
      event_name    TEXT,
      trigger       TEXT,
      member_id     TEXT,
      member_name   TEXT,
      member_login  TEXT,
      role_name     TEXT,
      created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
    )`);
  await pool.query('CREATE INDEX IF NOT EXISTS idx_members_logs_created_at ON members_logs (created_at)');
  await pool.query('CREATE INDEX IF NOT EXISTS idx_members_logs_member_id ON members_logs (member_id)');

  console.log('✅ PostgreSQL подключён, таблицы event_logs / count_logs / members_logs готовы.');
  return pool;
}

const s = (v) => (v != null ? String(v) : null);

export async function logEvent({ event_type, guild_id = null, channel_id = null, user_id = null, user_name = null, detail = null }) {
  if (!pool) return;
  try {
    await pool.query(
      `INSERT INTO event_logs (event_type, guild_id, channel_id, user_id, user_name, detail)
       VALUES ($1, $2, $3, $4, $5, $6)`,
      [event_type, s(guild_id), s(channel_id), s(user_id), user_name, detail],
    );
  } catch (e) {
    console.log(`⚠️ Ошибка записи в event_logs: ${e.message}`);
  }
}

export async function logCount({ guild_id, channel_id, channel_name, event_name, trigger, total, roles }) {
  if (!pool) return;
  try {
    await pool.query(
      `INSERT INTO count_logs (guild_id, channel_id, channel_name, event_name, trigger, total, roles)
       VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)`,
      [s(guild_id), s(channel_id), channel_name, event_name, trigger, Number(total), JSON.stringify(roles || {})],
    );
  } catch (e) {
    console.log(`⚠️ Ошибка записи в count_logs: ${e.message}`);
  }
}

export async function logMembers(members) {
  // members — массив объектов с полями guild_id, channel_id, channel_name,
  // event_name, trigger, member_id, member_name, member_login, role_name.
  if (!pool || !members.length) return;
  try {
    const cols = 9;
    const params = [];
    const tuples = members.map((m, i) => {
      const b = i * cols;
      params.push(
        s(m.guild_id), s(m.channel_id), m.channel_name ?? null,
        m.event_name ?? null, m.trigger ?? null, s(m.member_id),
        m.member_name ?? null, m.member_login ?? null, m.role_name ?? null,
      );
      return `($${b + 1},$${b + 2},$${b + 3},$${b + 4},$${b + 5},$${b + 6},$${b + 7},$${b + 8},$${b + 9})`;
    });
    await pool.query(
      `INSERT INTO members_logs
        (guild_id, channel_id, channel_name, event_name, trigger, member_id, member_name, member_login, role_name)
       VALUES ${tuples.join(',')}`,
      params,
    );
  } catch (e) {
    console.log(`⚠️ Ошибка записи в members_logs: ${e.message}`);
  }
}

export async function closeDb() {
  if (pool) await pool.end();
}
