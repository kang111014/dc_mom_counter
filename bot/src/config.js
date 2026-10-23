import { fileURLToPath } from 'node:url';
import dotenv from 'dotenv';

dotenv.config({ path: fileURLToPath(new URL('../../.env', import.meta.url)), quiet: true });

function required(name) {
  const value = process.env[name]?.trim();
  if (!value) {
    console.error(`.env 缺少 ${name}，請參考 .env.example 填寫`);
    process.exit(1);
  }
  return value;
}

export const config = {
  token: required('DISCORD_TOKEN'),
  guildId: required('GUILD_ID'),
  ownerId: required('OWNER_ID'),
  serviceUrl: `http://127.0.0.1:${process.env.SERVICE_PORT?.trim() || '8765'}`,
};
