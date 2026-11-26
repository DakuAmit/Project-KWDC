import AsyncStorage from '@react-native-async-storage/async-storage';

const DEFAULT_API_URL = '';
const API_KEY = 'kwdc_mobile_api_url';
const TOKEN_KEY = 'kwdc_mobile_token';
const USER_KEY = 'kwdc_mobile_user';
const MODE_KEY = 'kwdc_mobile_mode'; // 'user' | 'driver'

export function normalizeBaseUrl(raw) {
  let u = (raw || '').trim();
  if (!u) return '';
  if (!/^https?:\/\//i.test(u)) {
    u = 'https://' + u;
  }
  try {
    const parsed = new URL(u);
    return parsed.origin;
  } catch {
    return u.replace(/\/+$/, '');
  }
}

export async function getApiBaseUrl() {
  const saved = await AsyncStorage.getItem(API_KEY);
  return normalizeBaseUrl(saved || DEFAULT_API_URL);
}

export async function setApiBaseUrl(url) {
  const clean = normalizeBaseUrl(url);
  await AsyncStorage.setItem(API_KEY, clean);
  return clean;
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
  if (!base || base.includes('your-vercel-project.vercel.app')) {
    throw new Error('Please paste your real Vercel app URL (or http://<laptop-ip>:8000) in Backend Server URL and tap Save & Test.');
  }
  const authToken = token || (await AsyncStorage.getItem(TOKEN_KEY));
  const headers = { 'Content-Type': 'application/json' };
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

  const fullUrl = `${base}${path}`;
  const res = await fetch(fullUrl, {
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
    if (res.status === 404 && String(text).includes('NOT_FOUND')) {
      throw new Error(`Endpoint 404 at ${fullUrl}. Check that Backend Server URL is the root Vercel domain (without /admin or /client).`);
    }
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
