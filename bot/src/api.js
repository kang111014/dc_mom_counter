// 呼叫本機 Python 服務
import { config } from './config.js';

export class ApiError extends Error {}

export async function call(method, path, body) {
  let res;
  try {
    res = await fetch(config.serviceUrl + path, {
      method,
      headers: body ? { 'content-type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError('Python 服務沒有回應，請確認它有啟動');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(typeof data.detail === 'string' ? data.detail : `Python 服務錯誤（HTTP ${res.status}）`);
  }
  return data;
}

export async function sendAudio(userId, userName, pcm) {
  const query = new URLSearchParams({ user_id: userId, user_name: userName });
  await fetch(`${config.serviceUrl}/audio?${query}`, {
    method: 'POST',
    headers: { 'content-type': 'application/octet-stream' },
    body: pcm,
  });
}
