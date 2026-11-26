import AsyncStorage from '@react-native-async-storage/async-storage';

const DEFAULT_API_URL = 'https://your-vercel-project.vercel.app';
const API_KEY = 'kwdc_mobile_api_url';
const TOKEN_KEY = 'kwdc_mobile_token';
const USER_KEY = 'kwdc_mobile_user';
const MODE_KEY = 'kwdc_mobile_mode'; // 'user' | 'driver'

export async function getApiBaseUrl() {
  const saved = await AsyncStorage.getItem(API_KEY);
  return (saved || DEFAULT_API_URL).replace(/\/+$/, '');
}

export async function setApiBaseUrl(url) {
  await AsyncStorage.setItem(API_KEY, url.trim().replace(/\/+$/, ''));
}

export async function saveSession({ token, user, mode = 'user' }) {
  await AsyncStorage.setItem(TOKEN_KEY, token);
  await AsyncStorage.setItem(USER_KEY, JSON.stringify(user));
  await AsyncStorage.setItem(MODE_KEY, mode);
}

export async function loadSession() {
  const [token, userStr, mode] = await Promise.all([
    AsyncStorage.getItem(TOKEN_KEY),
    AsyncStorage.getItem(USER_KEY),
    AsyncStorage.getItem(MODE_KEY),
  ]);
  if (!token || !userStr) return null;
  return { token, user: JSON.parse(userStr), mode: mode || 'user' };
}

export async function clearSession() {
  await AsyncStorage.multiRemove([TOKEN_KEY, USER_KEY, MODE_KEY]);
}

export async function apiRequest(path, { method = 'GET', body = null, token = null } = {}) {
  const base = await getApiBaseUrl();
  const authToken = token || (await AsyncStorage.getItem(TOKEN_KEY));
  const headers = { 'Content-Type': 'application/json' };
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

  const res = await fetch(`${base}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = { detail: text || `HTTP ${res.status}` };
  }
  if (!res.ok) {
    throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data));
  }
  return data;
}

export async function uploadBase64Image({ filename, base64, mimeType = 'image/jpeg' }) {
  const res = await apiRequest('/api/uploads/image-base64', {
    method: 'POST',
    body: {
      filename,
      content_type: mimeType,
      data_base64: base64,
    },
  });
  return res.url; // e.g. /api/uploads/media/12
}
