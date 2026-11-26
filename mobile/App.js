import React, { useEffect, useState } from 'react';
import { SafeAreaView, View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { loadSession, clearSession } from './src/api/client';
import LoginScreen from './src/screens/LoginScreen';
import ClientHomeScreen from './src/screens/ClientHomeScreen';
import OwnerHomeScreen from './src/screens/OwnerHomeScreen';
import EquipmentHomeScreen from './src/screens/EquipmentHomeScreen';
import FleetDriverScreen from './src/screens/FleetDriverScreen';
import InchargeHomeScreen from './src/screens/InchargeHomeScreen';

export default function App() {
  const [session, setSession] = useState(null);
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    loadSession().then((s) => {
      setSession(s);
      setBooting(false);
    });
  }, []);

  async function handleLogout() {
    await clearSession();
    setSession(null);
  }

  if (booting) {
    return (
      <SafeAreaView style={styles.center}>
        <ActivityIndicator size="large" color="#0f172a" />
      </SafeAreaView>
    );
  }

  if (!session) {
    return (
      <SafeAreaView style={styles.root}>
        <StatusBar style="dark" />
        <LoginScreen onAuthenticated={setSession} />
      </SafeAreaView>
    );
  }

  const role = session.mode === 'driver' ? 'driver_cab' : (session.user?.user_role || session.user?.role || 'commercial_client');

  let ScreenComp = ClientHomeScreen;
  if (role === 'property_owner') ScreenComp = OwnerHomeScreen;
  else if (role === 'equipment_owner') ScreenComp = EquipmentHomeScreen;
  else if (role === 'fleet_partner' || role === 'driver_cab') ScreenComp = FleetDriverScreen;
  else if (role === 'warehouse_incharge') ScreenComp = InchargeHomeScreen;

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar style="light" />
      <View style={styles.topBar}>
        <View>
          <Text style={styles.topName}>{session.user?.full_name || 'KTM-WDC User'}</Text>
          <Text style={styles.topRole}>{role.replace('_', ' ').toUpperCase()}</Text>
        </View>
        <TouchableOpacity onPress={handleLogout} style={styles.logoutBtn}>
          <Text style={styles.logoutText}>Sign Out</Text>
        </TouchableOpacity>
      </View>
      <ScreenComp session={session} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#f8fafc' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  topBar: {
    backgroundColor: '#0f172a',
    paddingHorizontal: 16,
    paddingVertical: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  topName: { color: '#fff', fontSize: 15, fontWeight: '800' },
  topRole: { color: '#f59e0b', fontSize: 10, fontWeight: '800', marginTop: 2 },
  logoutBtn: { backgroundColor: '#1e293b', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 10 },
  logoutText: { color: '#e2e8f0', fontSize: 12, fontWeight: '700' },
});
