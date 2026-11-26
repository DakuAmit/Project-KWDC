import React, { useEffect, useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, ScrollView, StyleSheet, Alert, ActivityIndicator
} from 'react-native';
import { apiRequest, getApiBaseUrl, setApiBaseUrl, saveSession } from '../api/client';

export default function LoginScreen({ onAuthenticated }) {
  const [apiUrl, setApiUrl] = useState('');
  const [loginTab, setLoginTab] = useState('account'); // 'account' | 'driver'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [driverPhone, setDriverPhone] = useState('');
  const [driverPin, setDriverPin] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getApiBaseUrl().then((u) => {
      if (u && !u.includes('your-vercel-project.vercel.app')) setApiUrl(u);
    });
  }, []);

  async function saveServerUrl() {
    if (!apiUrl.trim()) {
      Alert.alert('Enter URL', 'Paste your live Vercel URL (e.g. https://project-kwdc.vercel.app) or http://192.168.x.x:8000');
      return;
    }
    const clean = await setApiBaseUrl(apiUrl);
    setApiUrl(clean);
    try {
      const health = await apiRequest('/health');
      Alert.alert('Connected!', `Server: ${clean}\nDB: ${health.database || 'OK'}`);
    } catch (err) {
      Alert.alert('Saved (Check Server)', `Saved URL: ${clean}\n\n${err.message}`);
    }
  }

  async function handleAccountLogin() {
    if (!email.trim() || !password) {
      Alert.alert('Required', 'Please enter your registered email and password.');
      return;
    }
    setLoading(true);
    try {
      await setApiBaseUrl(apiUrl);
      const data = await apiRequest('/api/auth/login', {
        method: 'POST',
        body: { email: email.trim().toLowerCase(), password },
      });
      await saveSession({ token: data.access_token, user: data, mode: 'user' });
      onAuthenticated({ token: data.access_token, user: data, mode: 'user' });
    } catch (err) {
      Alert.alert('Login Failed', err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleDriverPinLogin() {
    if (!driverPhone.trim() || !driverPin.trim()) {
      Alert.alert('Required', 'Enter mobile number and 4-6 digit Driver PIN.');
      return;
    }
    setLoading(true);
    try {
      await setApiBaseUrl(apiUrl);
      const data = await apiRequest('/api/fleet/driver/login', {
        method: 'POST',
        body: { phone_number: driverPhone.trim(), pin: driverPin.trim() },
      });
      const driverProfile = data.driver || data;
      await saveSession({ token: data.access_token, user: driverProfile, mode: 'driver' });
      onAuthenticated({ token: data.access_token, user: driverProfile, mode: 'driver' });
    } catch (err) {
      Alert.alert('Driver Login Failed', err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.brandBox}>
        <Text style={styles.badge}>KTM-WDC NEPAL MOBILE</Text>
        <Text style={styles.title}>Logistics &amp; Warehouse SuperApp</Text>
        <Text style={styles.sub}>Client • Property Owner • Equipment • Fleet/Driver • Incharge</Text>
      </View>

      {/* Server Endpoint Configurator (Works with Vercel or Local Wi-Fi) */}
      <View style={styles.card}>
        <Text style={styles.label}>Backend Server URL (Vercel or Laptop IP)</Text>
        <View style={styles.row}>
          <TextInput
            value={apiUrl}
            onChangeText={setApiUrl}
            autoCapitalize="none"
            placeholder="https://your-live-app.vercel.app"
            style={[styles.input, { flex: 1, marginBottom: 0 }]}
          />
          <TouchableOpacity onPress={saveServerUrl} style={styles.smallBtn}>
            <Text style={styles.smallBtnText}>Save &amp; Test</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Login Mode Switch */}
      <View style={styles.tabRow}>
        <TouchableOpacity
          onPress={() => setLoginTab('account')}
          style={[styles.tabBtn, loginTab === 'account' && styles.tabActive]}
        >
          <Text style={[styles.tabText, loginTab === 'account' && styles.tabTextActive]}>
            Partner / Client Login
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={() => setLoginTab('driver')}
          style={[styles.tabBtn, loginTab === 'driver' && styles.tabActive]}
        >
          <Text style={[styles.tabText, loginTab === 'driver' && styles.tabTextActive]}>
            Driver PIN Terminal
          </Text>
        </TouchableOpacity>
      </View>

      {loginTab === 'account' ? (
        <View style={styles.card}>
          <Text style={styles.hint}>
            Routes automatically to Client, Property Owner, Equipment Owner, Fleet Manager, or Warehouse Incharge.
          </Text>
          <Text style={styles.label}>Email Address</Text>
          <TextInput
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
            placeholder="you@company.com"
            style={styles.input}
          />
          <Text style={styles.label}>Password</Text>
          <TextInput
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            placeholder="••••••••"
            style={styles.input}
          />
          <TouchableOpacity onPress={handleAccountLogin} disabled={loading} style={styles.primaryBtn}>
            {loading ? <ActivityIndicator color="#0f172a" /> : <Text style={styles.primaryBtnText}>Sign In to Cockpit</Text>}
          </TouchableOpacity>
        </View>
      ) : (
        <View style={styles.card}>
          <Text style={styles.hint}>
            For Individual &amp; Commercial Drivers using Phone + 4-digit Cab PIN (live GPS + camera e-POD).
          </Text>
          <Text style={styles.label}>Registered Mobile Number</Text>
          <TextInput
            value={driverPhone}
            onChangeText={setDriverPhone}
            keyboardType="phone-pad"
            placeholder="+977-98XXXXXXXX"
            style={styles.input}
          />
          <Text style={styles.label}>Driver 4-6 Digit PIN</Text>
          <TextInput
            value={driverPin}
            onChangeText={setDriverPin}
            keyboardType="number-pad"
            secureTextEntry
            maxLength={6}
            placeholder="1234"
            style={styles.input}
          />
          <TouchableOpacity onPress={handleDriverPinLogin} disabled={loading} style={styles.primaryBtn}>
            {loading ? <ActivityIndicator color="#0f172a" /> : <Text style={styles.primaryBtnText}>Launch Driver Cab App</Text>}
          </TouchableOpacity>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: 20, backgroundColor: '#f8fafc', justifyContent: 'center' },
  brandBox: { backgroundColor: '#0f172a', padding: 20, borderRadius: 18, marginBottom: 16 },
  badge: { color: '#f59e0b', fontSize: 11, fontWeight: '800', letterSpacing: 1 },
  title: { color: '#ffffff', fontSize: 20, fontWeight: '800', marginTop: 4 },
  sub: { color: '#94a3b8', fontSize: 12, marginTop: 4 },
  card: { backgroundColor: '#ffffff', padding: 16, borderRadius: 16, borderWidth: 1, borderColor: '#e2e8f0', marginBottom: 14 },
  label: { fontSize: 12, fontWeight: '700', color: '#0f172a', marginBottom: 6 },
  hint: { fontSize: 11, color: '#64748b', marginBottom: 12 },
  input: { borderWidth: 1, borderColor: '#cbd5e1', borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, marginBottom: 12, backgroundColor: '#fff' },
  row: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  smallBtn: { backgroundColor: '#0f172a', paddingHorizontal: 14, paddingVertical: 11, borderRadius: 12 },
  smallBtnText: { color: '#fff', fontWeight: '700', fontSize: 12 },
  tabRow: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  tabBtn: { flex: 1, paddingVertical: 10, borderRadius: 12, backgroundColor: '#e2e8f0', alignItems: 'center' },
  tabActive: { backgroundColor: '#0f172a' },
  tabText: { fontSize: 12, fontWeight: '700', color: '#475569' },
  tabTextActive: { color: '#ffffff' },
  primaryBtn: { backgroundColor: '#f59e0b', paddingVertical: 14, borderRadius: 12, alignItems: 'center', marginTop: 4 },
  primaryBtnText: { color: '#0f172a', fontWeight: '900', fontSize: 14 },
});
