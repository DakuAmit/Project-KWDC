/**
 * KTM-WDC Centralized Frontend API Service
 * Connects the decoupled client to FastAPI backend endpoints
 */
const API_BASE = window.location.origin.includes('localhost') || window.location.origin.includes('127.0.0.1')
    ? 'http://127.0.0.1:8000'
    : '';

const KWDC_API = {
    getToken() {
        return localStorage.getItem('kwdc_token') || '';
    },

    setToken(token) {
        localStorage.setItem('kwdc_token', token);
    },

    getUser() {
        const u = localStorage.getItem('kwdc_user');
        return u ? JSON.parse(u) : null;
    },

    setUser(user) {
        localStorage.setItem('kwdc_user', JSON.stringify(user));
    },

    logout() {
        localStorage.removeItem('kwdc_token');
        localStorage.removeItem('kwdc_user');
        window.location.href = '/login.html';
    },

    async request(endpoint, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            ...(options.headers || {})
        };
        const token = this.getToken();
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
        try {
            const res = await fetch(url, { ...options, headers });
            if (res.status === 401 && !endpoint.includes('/login')) {
                this.logout();
                return null;
            }
            return res;
        } catch (err) {
            console.error('API Request Failure:', err);
            throw err;
        }
    },

    async login(email, password) {
        const res = await this.request('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email, password })
        });
        if (res && res.ok) {
            const data = await res.json();
            this.setToken(data.access_token);
            this.setUser(data.user);
            return data;
        }
        return null;
    },

    async register(userData) {
        const res = await this.request('/api/auth/register', {
            method: 'POST',
            body: JSON.stringify(userData)
        });
        if (res && res.ok) {
            const data = await res.json();
            this.setToken(data.access_token);
            this.setUser(data.user);
            return data;
        }
        return null;
    },

    async calculatePrice(distance, vehicleType = 'truck', stopsCount = 1) {
        const res = await this.request('/dispatch/calculate-price', {
            method: 'POST',
            body: JSON.stringify({
                distance: parseFloat(distance),
                vehicle_type: vehicleType,
                stops_count: parseInt(stopsCount)
            })
        });
        if (res && res.ok) {
            return await res.json();
        }
        return null;
    },

    async chatAI(message) {
        const res = await this.request('/ai/chat', {
            method: 'POST',
            body: JSON.stringify({ message })
        });
        if (res && res.ok) {
            return await res.json();
        }
        return { reply: 'AI service temporarily in fallback mode.' };
    }
};

window.KWDC_API = KWDC_API;
