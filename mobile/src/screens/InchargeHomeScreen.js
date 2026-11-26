import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, StyleSheet, Alert } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { apiRequest } from '../api/client';

export default function InchargeHomeScreen() {
  const [warehouses, setWarehouses] = useState([]);
  const [scanning, setScanning] = useState(false);
  const [permission, requestPermission] = useCameraPermissions();
  const [scannedToken, setScannedToken] = useState('');
  const [summary, setSummary] = useState('');

  async function refresh() {
    try {
      const list = await apiRequest('/api/incharge/my-warehouses');
      setWarehouses(Array.isArray(list) ? list : []);
    } catch (err) {
      Alert.alert('Load Error', err.message);
    }
  }

  useEffect(() => { refresh(); }, []);

  async function openQrScanner() {
    if (!permission?.granted) {
      const res = await requestPermission();
      if (!res.granted) return Alert.alert('Camera Needed', 'Grant camera access to scan Gate Pass QR codes.');
    }
    setScanning(true);
  }

  function handleBarcode({ data }) {
    setScanning(false);
    setScannedToken(data);
    Alert.alert('QR Scanned', `Token read:\n${data}`);
  }

  async function submitShiftLog() {
    const whId = warehouses[0]?.warehouse_id || 1;
    if (!summary.trim()) return Alert.alert('Required', 'Enter shift check summary.');
    try {
      const res = await apiRequest('/api/incharge/activity-log', {
        method: 'POST',
        body: {
          warehouse_id: whId,
          log_type: 'DAILY_SUMMARY',
          summary: summary.trim(),
          detailed_notes: scannedToken ? `QR Verified Token: ${scannedToken} | ${summary.trim()}` : summary.trim(),
        },
      });
      Alert.alert('Logged', res.message || 'Shift log sent to SuperAdmin & Property Owner.');
      setSummary('');
    } catch (err) {
      Alert.alert('Error', err.message);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.wrap}>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Native Gate Pass &amp; Stock QR Scanner</Text>
        <Text style={styles.meta}>Scan Client ISO/IEC 18004 Stock or Gate Pass QR tokens directly at the warehouse gate.</Text>
        {scanning ? (
          <View style={styles.camBox}>
            <CameraView
              style={{ flex: 1 }}
              barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
              onBarcodeScanned={handleBarcode}
            />
            <TouchableOpacity onPress={() => setScanning(false)} style={styles.btnDark}>
              <Text style={styles.btnLight}>Cancel Scan</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <TouchableOpacity onPress={openQrScanner} style={[styles.btnAmber, { marginTop: 10 }]}>
            <Text style={styles.btnDarkText}>Open Camera QR Scanner</Text>
          </TouchableOpacity>
        )}
        {!!scannedToken && <Text style={styles.price}>Last Scanned QR: {scannedToken}</Text>}
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Submit Daily Inspection / Gate Audit</Text>
        <TextInput value={summary} onChangeText={setSummary} placeholder="e.g. Gate GP-2083 cleared, CCTV online" style={styles.input} />
        <TouchableOpacity onPress={submitShiftLog} style={[styles.btnDark, { marginTop: 8 }]}>
          <Text style={styles.btnLight}>Transmit Inspection Report</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 14, paddingBottom: 40 },
  card: { backgroundColor: '#fff', padding: 14, borderRadius: 14, borderWidth: 1, borderColor: '#e2e8f0', marginBottom: 12 },
  cardTitle: { fontSize: 14, fontWeight: '800', color: '#0f172a' },
  meta: { fontSize: 11, color: '#64748b', marginTop: 3 },
  price: { fontSize: 12, fontWeight: '800', color: '#047857', marginTop: 8 },
  camBox: { height: 240, borderRadius: 12, overflow: 'hidden', marginTop: 10 },
  input: { borderWidth: 1, borderColor: '#cbd5e1', borderRadius: 10, padding: 9, marginTop: 8, fontSize: 12 },
  btnDark: { backgroundColor: '#0f172a', padding: 11, borderRadius: 10, alignItems: 'center' },
  btnAmber: { backgroundColor: '#f59e0b', padding: 12, borderRadius: 10, alignItems: 'center' },
  btnLight: { color: '#fff', fontWeight: '700', fontSize: 12 },
  btnDarkText: { color: '#0f172a', fontWeight: '900', fontSize: 12 },
});
