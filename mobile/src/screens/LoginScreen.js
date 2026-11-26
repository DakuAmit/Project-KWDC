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
  const [authSubMode, setAuthSubMode] = useState('signin'); // 'signin' | 'register' | 'verify' | 'forgot' | 'reset'
  const [regName, setRegName] = useState('');
  const [regPhone, setRegPhone] = useState('');
  const [regRole, setRegRole] = useState('commercial_client');
  const [otpInput, setOtpInput] = useState('');
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

  async function handleRegisterMobile() {
    if (!regName.trim() || !email.trim() || !regPhone.trim() || password.length < 6) {
      return Alert.alert('Required', 'Fill Full Name, Email, Nepal Phone, and 6+ char Password.');
    }
    setLoading(true);
    try {
      await setApiBaseUrl(apiUrl);
      const res = await apiRequest('/api/auth/register', {
        method: 'POST',
        body: {
          full_name: regName.trim(),
          email: email.trim().toLowerCase(),
          phone_number: regPhone.trim(),
          operating_location: 'Kathmandu Valley',
          role: regRole,
          password,
          confirm_password: password,
        },
      });
      Alert.alert('OTP Dispatched', res.message || 'Check Email / SMS for 6-digit OTP.');
      setAuthSubMode('verify');
    } catch (err) {
      Alert.alert('Register Failed', err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyOtpMobile() {
    if (otpInput.trim().length !== 6) return Alert.alert('OTP Required', 'Enter the 6-digit verification code.');
    setLoading(true);
    try {
      const data = await apiRequest('/api/auth/verify-otp', {
        method: 'POST',
        body: { email: email.trim().toLowerCase(), otp_code: otpInput.trim() },
      });
      await saveSession({ token: data.access_token, user: data, mode: 'user' });
      onAuthenticated({ token: data.access_token, user: data, mode: 'user' });
    } catch (err) {
      Alert.alert('Verification Failed', err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleForgotPasswordMobile() {
    if (!email.trim()) return Alert.alert('Email Required', 'Enter your registered email address.');
    setLoading(true);
    try {
      await setApiBaseUrl(apiUrl);
      const res = await apiRequest('/api/auth/forgot-password', {
        method: 'POST',
        body: { email: email.trim().toLowerCase() },
      });
      Alert.alert('Reset Code Sent', res.message);
      setAuthSubMode('reset');
    } catch (err) {
      Alert.alert('Reset Failed', err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleResetPasswordMobile() {
    if (otpInput.trim().length !== 6 || password.length < 6) {
      return Alert.alert('Invalid Input', 'Enter the 6-digit OTP and new 6+ char password.');
    }
    setLoading(true);
    try {
      const res = await apiRequest('/api/auth/reset-password', {
        method: 'POST',
        body: { email: email.trim().toLowerCase(), otp_code: otpInput.trim(), new_password: password, confirm_password: password },
      });
      Alert.alert('Success', res.message || 'Password updated!');
      setAuthSubMode('signin');
    } catch (err) {
      Alert.alert('Reset Error', err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleDriverPinLogin() {
    if (!driverPhone.trim() || !driverPin.trim()) {
      Alert.alert('Required', 'Enter mobile number and 4-6 digit PIN.');
      return;
    }
    setLoading(true);
    try {
      await setApiBaseUrl(apiUrl);
      if (loginTab === 'eq_operator') {
        const data = await apiRequest('/api/equipment/operator/login', {
          method: 'POST',
          body: { phone_number: driverPhone.trim(), pin: driverPin.trim() },
        });
        const opProfile = data.operator || data;
        await saveSession({ token: data.access_token, user: opProfile, mode: 'equipment_operator' });
        onAuthenticated({ token: data.access_token, user: opProfile, mode: 'equipment_operator' });
      } else {
        const data = await apiRequest('/api/fleet/driver/login', {
          method: 'POST',
          body: { phone_number: driverPhone.trim(), pin: driverPin.trim() },
        });
        const driverProfile = data.driver || data;
        await saveSession({ token: data.access_token, user: driverProfile, mode: 'driver' });
        onAuthenticated({ token: data.access_token, user: driverProfile, mode: 'driver' });
      }
    } catch (err) {
      Alert.alert('PIN Login Failed', err.message);
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
          <Text style={[styles.tabText, loginTab === 'account' && styles.tabTextActive]}>Partner / Client</Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={() => setLoginTab('driver')}
          style={[styles.tabBtn, loginTab === 'driver' && styles.tabActive]}
        >
          <Text style={[styles.tabText, loginTab === 'driver' && styles.tabTextActive]}>Driver PIN</Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={() => setLoginTab('eq_operator')}
          style={[styles.tabBtn, loginTab === 'eq_operator' && styles.tabActive]}
        >
          <Text style={[styles.tabText, loginTab === 'eq_operator' && styles.tabTextActive]}>Equipment Op PIN</Text>
        </TouchableOpacity>
      </View>

      {loginTab === 'account' ? (
        <View style={styles.card}>
          <View style={styles.tabRow}>
            {[['signin', 'Sign In'], ['register', 'Register'], ['forgot', 'Reset PW']].map(([m, t]) => (
              <TouchableOpacity key={m} onPress={() => setAuthSubMode(m)} style={[styles.tabBtn, authSubMode === m && styles.tabActive]}>
                <Text style={[styles.tabText, authSubMode === m && styles.tabTextActive]}>{t}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {authSubMode === 'signin' && (
            <View>
              <Text style={styles.hint}>Routes automatically to Client, Property Owner, Equipment Owner, Fleet Manager, or Incharge.</Text>
              <Text style={styles.label}>Email Address</Text>
              <TextInput value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" placeholder="you@company.com" style={styles.input} />
              <Text style={styles.label}>Password</Text>
              <TextInput value={password} onChangeText={setPassword} secureTextEntry placeholder="••••••••" style={styles.input} />
              <TouchableOpacity onPress={handleAccountLogin} disabled={loading} style={styles.primaryBtn}>
                {loading ? <ActivityIndicator color="#0f172a" /> : <Text style={styles.primaryBtnText}>Sign In to Cockpit</Text>}
              </TouchableOpacity>
            </View>
          )}

          {authSubMode === 'register' && (
            <View>
              <Text style={styles.label}>Account Role</Text>
              <View style={[styles.row, { flexWrap: 'wrap', marginBottom: 8 }]}>
                {[['commercial_client', 'Client'], ['property_owner', 'Owner'], ['fleet_partner', 'Fleet'], ['equipment_owner', 'Equipment']].map(([rv, rl]) => (
                  <TouchableOpacity key={rv} onPress={() => setRegRole(rv)} style={[styles.smallBtn, regRole === rv ? { backgroundColor: '#f59e0b' } : { backgroundColor: '#64748b' }]}>
                    <Text style={{ color: regRole === rv ? '#0f172a' : '#fff', fontSize: 11, fontWeight: '800' }}>{rl}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <TextInput value={regName} onChangeText={setRegName} placeholder="Full Name / Organization" style={styles.input} />
              <TextInput value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" placeholder="Email Address" style={styles.input} />
              <TextInput value={regPhone} onChangeText={setRegPhone} keyboardType="phone-pad" placeholder="98XXXXXXXX" style={styles.input} />
              <TextInput value={password} onChangeText={setPassword} secureTextEntry placeholder="Password (6+ chars)" style={styles.input} />
              <TouchableOpacity onPress={handleRegisterMobile} disabled={loading} style={styles.primaryBtn}>
                <Text style={styles.primaryBtnText}>Register &amp; Send OTP</Text>
              </TouchableOpacity>
            </View>
          )}

          {authSubMode === 'verify' && (
            <View>
              <Text style={styles.hint}>Enter the 6-digit OTP dispatched to {email}.</Text>
              <TextInput value={otpInput} onChangeText={setOtpInput} keyboardType="number-pad" maxLength={6} placeholder="6-digit OTP" style={styles.input} />
              <TouchableOpacity onPress={handleVerifyOtpMobile} disabled={loading} style={styles.primaryBtn}>
                <Text style={styles.primaryBtnText}>Verify OTP &amp; Enter App</Text>
              </TouchableOpacity>
            </View>
          )}

          {authSubMode === 'forgot' && (
            <View>
              <Text style={styles.hint}>Send a 6-digit reset code to your Email + SMS.</Text>
              <TextInput value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" placeholder="Registered Email" style={styles.input} />
              <TouchableOpacity onPress={handleForgotPasswordMobile} disabled={loading} style={styles.primaryBtn}>
                <Text style={styles.primaryBtnText}>Send Password Reset OTP</Text>
              </TouchableOpacity>
            </View>
          )}

          {authSubMode === 'reset' && (
            <View>
              <TextInput value={otpInput} onChangeText={setOtpInput} keyboardType="number-pad" maxLength={6} placeholder="6-digit Reset OTP" style={styles.input} />
              <TextInput value={password} onChangeText={setPassword} secureTextEntry placeholder="New Password (6+ chars)" style={styles.input} />
              <TouchableOpacity onPress={handleResetPasswordMobile} disabled={loading} style={styles.primaryBtn}>
                <Text style={styles.primaryBtnText}>Save New Password</Text>
              </TouchableOpacity>
            </View>
          )}
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
