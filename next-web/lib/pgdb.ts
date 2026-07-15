import { Pool } from "pg";

let connectionString = process.env.POSTGRES_DB_URL;

if (!connectionString) {
  const host = process.env.POSTGRES_HOST;
  const password = process.env.POSTGRES_PASSWORD;
  const user = process.env.POSTGRES_USER || "postgres";
  const db = process.env.POSTGRES_DB || "ed2k";
  const port = process.env.POSTGRES_PORT || "5433";

  if (!host || !password) {
    // eslint-disable-next-line no-console
    console.warn(
      "Missing environment variables `POSTGRES_DB_URL` or `POSTGRES_HOST` and `POSTGRES_PASSWORD`",
    );
  }

  connectionString = `postgres://${user}:${password}@${host}:${port}/${db}`;
}

export const pool = new Pool({
  connectionString,
  ssl: false,
  max: 10,
  connectionTimeoutMillis: 5000,
  idleTimeoutMillis: 30000,
});

export const query = (text: string, params?: any) => pool.query(text, params);
