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
        } else if (res) {
            let data = {};
            try {
                data = await res.json();
            } catch (_) {
                const text = await res.text().catch(() => '');
                data = { detail: text || `HTTP ${res.status}` };
            }
            const err = new Error(data.detail || 'Invalid email address or password.');
            err.status = res.status;
            err.data = data;
            throw err;
        }
        return null;
    },

    async register(userData) {
        const res = await this.request('/api/auth/register', {
            method: 'POST',
            body: JSON.stringify(userData)
        });
        if (res) {
            let data = {};
            try {
                data = await res.json();
            } catch (_) {
                const text = await res.text().catch(() => '');
                data = { detail: text || `HTTP ${res.status}` };
            }
            return { ok: res.ok, status: res.status, data };
        }
        return { ok: false, data: null };
    },

    async verifyCode(email, code) {
        const res = await this.request('/api/auth/verify-code', {
            method: 'POST',
            body: JSON.stringify({ email, code })
        });
        if (res) {
            let data = {};
            try {
                data = await res.json();
            } catch (_) {
                const text = await res.text().catch(() => '');
                data = { detail: text || `HTTP ${res.status}` };
            }
            if (res.ok && data.access_token) {
                this.setToken(data.access_token);
                this.setUser(data.user);
            }
            return { ok: res.ok, status: res.status, data };
        }
        return { ok: false, data: null };
    },

    async resendCode(email) {
        const res = await this.request('/api/auth/resend-code', {
            method: 'POST',
            body: JSON.stringify({ email })
        });
        if (res) {
            let data = {};
            try {
                data = await res.json();
            } catch (_) {
                const text = await res.text().catch(() => '');
                data = { detail: text || `HTTP ${res.status}` };
            }
            return { ok: res.ok, status: res.status, data };
        }
        return { ok: false, data: null };
    },

    getDashboardUrl(role) {
        const r = (role || 'client').toLowerCase();
        return `/dashboard.html?role=${encodeURIComponent(r)}`;
    },

    async getDashboardStats() {
        const res = await this.request('/api/dashboard/stats');
        if (res && res.ok) {
            return await res.json();
        }
        return null;
    },

    async calculatePrice(distance, vehicleType = 'truck', stopsCount = 1) {
        const res = await this.request('/api/dispatch/calculate-price', {
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
        const res = await this.request('/api/ai/chat', {
            method: 'POST',
            body: JSON.stringify({ message })
        });
        if (res && res.ok) {
            return await res.json();
        }
        return { reply: 'AI service temporarily in fallback mode.' };
    },

    // Real Warehousing API
    async getWarehouses() {
        const res = await this.request('/api/warehouses');
        if (res && res.ok) {
            return await res.json();
        }
        return [];
    },

    async createWarehouse(whData) {
        const res = await this.request('/api/warehouses', {
            method: 'POST',
            body: JSON.stringify(whData)
        });
        if (res) {
            let data = {};
            try { data = await res.json(); } catch(_) {}
            return { ok: res.ok, status: res.status, data };
        }
        return { ok: false, data: null };
    },

    async reserveWarehouse(warehouseId, payload) {
        const res = await this.request(`/api/warehouses/${warehouseId}/reserve`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        if (res) {
            let data = {};
            try { data = await res.json(); } catch(_) {}
            return { ok: res.ok, status: res.status, data };
        }
        return { ok: false, data: null };
    },

    // Real Invoices & IRD Tax Settlements
    async getInvoices() {
        const res = await this.request('/api/invoices');
        if (res && res.ok) {
            return await res.json();
        }
        return [];
    },

    async payInvoice(invoiceId, paymentMethod = 'esewa') {
        const res = await this.request(`/api/invoices/${invoiceId}/pay`, {
            method: 'POST',
            body: JSON.stringify({ payment_method: paymentMethod })
        });
        if (res) {
            let data = {};
            try { data = await res.json(); } catch(_) {}
            return { ok: res.ok, status: res.status, data };
        }
        return { ok: false, data: null };
    }
};

window.KWDC_API = KWDC_API;
