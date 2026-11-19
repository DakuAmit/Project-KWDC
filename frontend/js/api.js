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

    async createDispatch(orderData) {
        const res = await this.request('/api/dispatch/orders', {
            method: 'POST',
            body: JSON.stringify(orderData)
        });
        if (res) {
            let data = {};
            try { data = await res.json(); } catch(_) {}
            return { ok: res.ok, status: res.status, data };
        }
        return { ok: false, data: null };
    },

    async getDispatch(dispatchId) {
        const res = await this.request(`/api/dispatch/${dispatchId}`);
        return (res && res.ok) ? await res.json() : null;
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
    },

    // ==========================================
    // SuperAdmin Console & Drawer API Services
    // ==========================================
    async getAdminOverview() {
        const res = await this.request('/api/admin/overview');
        return (res && res.ok) ? await res.json() : null;
    },

    async getAdminUsers(role = '') {
        const url = role && role !== 'all' ? `/api/admin/users?role=${encodeURIComponent(role)}` : '/api/admin/users';
        const res = await this.request(url);
        return (res && res.ok) ? await res.json() : [];
    },

    async updateAdminUserStatus(userId, isActive) {
        const res = await this.request(`/api/admin/users/${userId}/status`, {
            method: 'POST',
            body: JSON.stringify({ is_active: isActive })
        });
        return (res && res.ok);
    },

    async verifyAdminUser(userId, isVerified) {
        const res = await this.request(`/api/admin/users/${userId}/verify`, {
            method: 'POST',
            body: JSON.stringify({ is_verified: isVerified })
        });
        return (res && res.ok);
    },

    async getAdminWarehouses() {
        const res = await this.request('/api/admin/warehouses');
        return (res && res.ok) ? await res.json() : [];
    },

    async updateAdminWarehouseStatus(warehouseId, status) {
        const res = await this.request(`/api/admin/warehouses/${warehouseId}/status`, {
            method: 'POST',
            body: JSON.stringify({ status })
        });
        return (res && res.ok);
    },

    async getAdminDispatches() {
        const res = await this.request('/api/admin/dispatches');
        return (res && res.ok) ? await res.json() : [];
    },

    async updateAdminDispatchStatus(dispatchId, status) {
        const res = await this.request(`/api/admin/dispatches/${dispatchId}/status`, {
            method: 'POST',
            body: JSON.stringify({ status })
        });
        return (res && res.ok);
    },

    async assignAdminDispatch(dispatchId, driverId) {
        const res = await this.request(`/api/admin/dispatches/${dispatchId}/assign`, {
            method: 'POST',
            body: JSON.stringify({ driver_id: parseInt(driverId) })
        });
        return (res && res.ok);
    },

    async getAdminTelemetry() {
        const res = await this.request('/api/admin/telemetry');
        return (res && res.ok) ? await res.json() : [];
    },

    async getAdminInventory() {
        const res = await this.request('/api/admin/inventory');
        return (res && res.ok) ? await res.json() : { total_boxes: 0, stocks: [] };
    },

    async getAdminEquipment() {
        const res = await this.request('/api/admin/equipment');
        return (res && res.ok) ? await res.json() : { equipment: [], jobs: [] };
    },

    async getAdminSecurity() {
        const res = await this.request('/api/admin/security');
        return (res && res.ok) ? await res.json() : { total_guards: 0, agencies: [], incidents: [] };
    },

    async updateAdminIncidentStatus(incidentId, status) {
        const res = await this.request(`/api/admin/security/incidents/${incidentId}/status`, {
            method: 'POST',
            body: JSON.stringify({ status })
        });
        return (res && res.ok);
    },

    async getAdminInvoices() {
        const res = await this.request('/api/admin/invoices');
        return (res && res.ok) ? await res.json() : { summary: {}, invoices: [] };
    },

    async getAdminSettings() {
        const res = await this.request('/api/admin/settings');
        return (res && res.ok) ? await res.json() : { margin_tiers: [], vehicle_tariffs: [] };
    },

    async createAdminMarginTier(tierData) {
        const res = await this.request('/api/admin/settings/margin-tiers', {
            method: 'POST',
            body: JSON.stringify(tierData)
        });
        return (res && res.ok);
    },

    async deleteAdminMarginTier(tierId) {
        const res = await this.request(`/api/admin/settings/margin-tiers/${tierId}`, {
            method: 'DELETE'
        });
        return (res && res.ok);
    },

    // ==========================================
    // Warehouse Property Owner API Services
    // ==========================================
    async getPropertyOverview() {
        const res = await this.request('/api/property-owner/overview');
        return (res && res.ok) ? await res.json() : null;
    },

    async updatePropertyRequest(requestId, status, adminNotes = '') {
        const res = await this.request(`/api/property-owner/requests/${requestId}`, {
            method: 'PATCH',
            body: JSON.stringify({ status, admin_notes: adminNotes })
        });
        if (res) {
            let data = {};
            try { data = await res.json(); } catch(_) {}
            return { ok: res.ok, status: res.status, data };
        }
        return { ok: false, data: null };
    },

    // ==========================================
    // Commercial Driver API Services
    // ==========================================
    async getDriverOverview() {
        const res = await this.request('/api/driver/overview');
        return (res && res.ok) ? await res.json() : null;
    },

    async updateDriverTelemetry(lat, lng, orderId = null, accuracy = 10.0) {
        const res = await this.request('/api/driver/telemetry', {
            method: 'POST',
            body: JSON.stringify({ latitude: lat, longitude: lng, order_id: orderId, accuracy })
        });
        if (res) {
            let data = {};
            try { data = await res.json(); } catch(_) {}
            return { ok: res.ok, status: res.status, data };
        }
        return { ok: false, data: null };
    },

    async updateDriverOrderStatus(orderId, status, notes = '') {
        const res = await this.request(`/api/driver/orders/${orderId}/status`, {
            method: 'PATCH',
            body: JSON.stringify({ status, admin_notes: notes })
        });
        if (res) {
            let data = {};
            try { data = await res.json(); } catch(_) {}
            return { ok: res.ok, status: res.status, data };
        }
        return { ok: false, data: null };
    },

    async submitDriverPOD(orderId, recipientName, notes = '') {
        const res = await this.request(`/api/driver/orders/${orderId}/pod`, {
            method: 'POST',
            body: JSON.stringify({ recipient_name: recipientName, delivery_notes: notes })
        });
        if (res) {
            let data = {};
            try { data = await res.json(); } catch(_) {}
            return { ok: res.ok, status: res.status, data };
        }
        return { ok: false, data: null };
    },

    // ==========================================
    // Heavy Equipment Owner API Services
    // ==========================================
    async getEquipmentOverview() {
        const res = await this.request('/api/equipment/overview');
        return (res && res.ok) ? await res.json() : null;
    },

    async createEquipment(eqData) {
        const res = await this.request('/api/equipment', {
            method: 'POST',
            body: JSON.stringify(eqData)
        });
        if (res) {
            let data = {};
            try { data = await res.json(); } catch(_) {}
            return { ok: res.ok, status: res.status, data };
        }
        return { ok: false, data: null };
    },

    async bookEquipment(equipmentId, bookingData) {
        const res = await this.request(`/api/equipment/${equipmentId}/book`, {
            method: 'POST',
            body: JSON.stringify(bookingData)
        });
        if (res) {
            let data = {};
            try { data = await res.json(); } catch(_) {}
            return { ok: res.ok, status: res.status, data };
        }
        return { ok: false, data: null };
    },

    async updateEquipmentJobStatus(jobId, status) {
        const res = await this.request(`/api/equipment/jobs/${jobId}/status`, {
            method: 'PATCH',
            body: JSON.stringify({ status })
        });
        if (res) {
            let data = {};
            try { data = await res.json(); } catch(_) {}
            return { ok: res.ok, status: res.status, data };
        }
        return { ok: false, data: null };
    },

    // ==========================================
    // Licensed Security Agency API Services (5 Use Cases)
    // ==========================================
    async getSecurityOverview() {
        const res = await this.request('/api/security/overview');
        return (res && res.ok) ? await res.json() : null;
    },

    async addSecurityGuard(guardData) {
        const res = await this.request('/api/security/guards', {
            method: 'POST',
            body: JSON.stringify(guardData)
        });
        if (res) {
            let data = {};
            try { data = await res.json(); } catch(_) {}
            return { ok: res.ok, status: res.status, data };
        }
        return { ok: false, data: null };
    },

    async deploySecurityGuard(assignmentData) {
        const res = await this.request('/api/security/assignments', {
            method: 'POST',
            body: JSON.stringify(assignmentData)
        });
        if (res) {
            let data = {};
            try { data = await res.json(); } catch(_) {}
            return { ok: res.ok, status: res.status, data };
        }
        return { ok: false, data: null };
    },

    async logSecurityIncident(incidentData) {
        const res = await this.request('/api/security/incidents', {
            method: 'POST',
            body: JSON.stringify(incidentData)
        });
        if (res) {
            let data = {};
            try { data = await res.json(); } catch(_) {}
            return { ok: res.ok, status: res.status, data };
        }
        return { ok: false, data: null };
    },

    async generateSecurityInvoice(invoiceData) {
        const res = await this.request('/api/security/invoices/generate', {
            method: 'POST',
            body: JSON.stringify(invoiceData)
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
