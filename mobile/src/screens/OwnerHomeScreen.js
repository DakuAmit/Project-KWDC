import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, StyleSheet, Alert } from 'react-native';
import * as Location from 'expo-location';
import * as ImagePicker from 'expo-image-picker';
import { apiRequest, uploadBase64Image } from '../api/client';

export default function OwnerHomeScreen() {
  const [listings, setListings] = useState([]);
  const [payouts, setPayouts] = useState([]);
  const [kycStatus, setKycStatus] = useState('PENDING_SUBMISSION');
  const [title, setTitle] = useState('');
  const [sqft, setSqft] = useState('3000');
  const [rate, setRate] = useState('45');
  const [coords, setCoords] = useState({ lat: 27.7172, lng: 85.3240 });
  const [photoUrl, setPhotoUrl] = useState('');

  async function refresh() {
    try {
      const [l, p, k] = await Promise.all([
        apiRequest('/api/warehouses/my-listings'),
        apiRequest('/api/warehouses/my-payouts'),
        apiRequest('/api/auth/kyc-profile'),
      ]);
      setListings(Array.isArray(l) ? l : []);
      setPayouts(Array.isArray(p) ? p : []);
      setKycStatus(k.kyc_status || 'PENDING_SUBMISSION');
    } catch (err) {
      Alert.alert('Load Error', err.message);
    }
  }

  useEffect(() => { refresh(); }, []);

  async function pinMyPhoneGps() {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') return Alert.alert('Permission Needed', 'Enable location access.');
    const loc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
    setCoords({ lat: loc.coords.latitude, lng: loc.coords.longitude });
    Alert.alert('GPS Pinned', `Lat: ${loc.coords.latitude.toFixed(5)}, Lng: ${loc.coords.longitude.toFixed(5)}`);
  }

  async function snapSpacePhoto() {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) return Alert.alert('Camera Needed', 'Enable camera permission.');
    const shot = await ImagePicker.launchCameraAsync({ quality: 0.5, base64: true });
    if (!shot.canceled && shot.assets?.[0]?.base64) {
      try {
        const url = await uploadBase64Image({ filename: 'warehouse.jpg', base64: shot.assets[0].base64 });
        setPhotoUrl(url);
        Alert.alert('Uploaded!', `Photo stored cleanly at ${url}`);
      } catch (err) {
        Alert.alert('Upload Failed', err.message);
      }
    }
  }

  async function submitSpace() {
    if (kycStatus !== 'VERIFIED') {
      Alert.alert('KYC Verification Pending', 'Please verify your KYC & Bank details first before registering a storage space.');
      return;
    }
    if (!title.trim()) return Alert.alert('Required', 'Enter Facility Title.');
    try {
      const res = await apiRequest('/api/warehouses/list-space', {
        method: 'POST',
        body: {
          title: title.trim(),
          space_type: 'dry_storage',
          input_value: parseFloat(sqft) || 2000,
          input_unit: 'sqft',
          base_rate_per_sqft: parseFloat(rate) || 45,
          district: 'Kathmandu',
          latitude: coords.lat,
          longitude: coords.lng,
          photo_urls: photoUrl ? [photoUrl] : undefined,
        },
      });
      Alert.alert('Submitted', res.message || 'Space sent for audit!');
      setTitle('');
      refresh();
    } catch (err) {
      Alert.alert('Blocked', err.message);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.wrap}>
      <View style={styles.kycBox}>
        <Text style={styles.kycTitle}>KYC &amp; Bank Status: {kycStatus}</Text>
        <Text style={styles.meta}>Property owners must be KYC verified before registering new godowns.</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Register Space via Mobile GPS &amp; Camera</Text>
        <TextInput value={title} onChangeText={setTitle} placeholder="Facility Title (e.g. Kalanki Shed #2)" style={styles.input} />
        <View style={styles.row}>
          <TextInput value={sqft} onChangeText={setSqft} keyboardType="numeric" placeholder="Sq Ft" style={[styles.input, { flex: 1 }]} />
          <TextInput value={rate} onChangeText={setRate} keyboardType="numeric" placeholder="Rs/sqft" style={[styles.input, { flex: 1 }]} />
        </View>
        <View style={styles.row}>
          <TouchableOpacity onPress={pinMyPhoneGps} style={styles.btnDark}><Text style={styles.btnLight}>Pin GPS ({coords.lat.toFixed(3)}, {coords.lng.toFixed(3)})</Text></TouchableOpacity>
          <TouchableOpacity onPress={snapSpacePhoto} style={styles.btnDark}><Text style={styles.btnLight}>{photoUrl ? 'Photo Ready ✓' : 'Snap Photo'}</Text></TouchableOpacity>
        </View>
        <TouchableOpacity onPress={submitSpace} style={[styles.btnAmber, { marginTop: 10 }]}>
          <Text style={styles.btnDarkText}>Submit for Physical Audit</Text>
        </TouchableOpacity>
      </View>

      <Text style={styles.secHdr}>My Spaces &amp; Occupancy Yield</Text>
      {listings.map((w) => (
        <View key={w.id} style={styles.card}>
          <Text style={styles.cardTitle}>{w.title}</Text>
          <Text style={styles.meta}>Occupied: {w.occupied_sqft}/{w.total_sqft} sq ft ({w.occupancy_percent}%)</Text>
          <Text style={styles.price}>Realized Yield: Rs. {w.realized_monthly_yield_npr} / Potential: Rs. {w.potential_monthly_yield_npr}</Text>
        </View>
      ))}

      <Text style={styles.secHdr}>Net Bank Payouts (After 10% Fee &amp; 10% Rent TDS)</Text>
      {payouts.map((p, idx) => (
        <View key={idx} style={styles.card}>
          <Text style={styles.cardTitle}>{p.warehouse_title} ({p.lease_number})</Text>
          <Text style={styles.meta}>Gross: Rs. {p.monthly_gross_rent} | TDS (10%): Rs. {p.tds_10pct}</Text>
          <Text style={styles.price}>Net Bank Deposit: Rs. {p.net_bank_deposit_npr}</Text>
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 14, paddingBottom: 40 },
  kycBox: { backgroundColor: '#fef3c7', padding: 12, borderRadius: 12, marginBottom: 12, borderWidth: 1, borderColor: '#fde68a' },
  kycTitle: { fontWeight: '800', fontSize: 13, color: '#92400e' },
  secHdr: { fontSize: 13, fontWeight: '800', color: '#0f172a', marginVertical: 8 },
  card: { backgroundColor: '#fff', padding: 14, borderRadius: 14, borderWidth: 1, borderColor: '#e2e8f0', marginBottom: 10 },
  cardTitle: { fontSize: 14, fontWeight: '800', color: '#0f172a' },
  meta: { fontSize: 11, color: '#64748b', marginTop: 3 },
  price: { fontSize: 12, fontWeight: '800', color: '#047857', marginTop: 4 },
  input: { borderWidth: 1, borderColor: '#cbd5e1', borderRadius: 10, padding: 9, marginTop: 6, fontSize: 12 },
  row: { flexDirection: 'row', gap: 8, marginTop: 8 },
  btnDark: { flex: 1, backgroundColor: '#0f172a', padding: 10, borderRadius: 10, alignItems: 'center' },
  btnAmber: { backgroundColor: '#f59e0b', padding: 12, borderRadius: 10, alignItems: 'center' },
  btnLight: { color: '#fff', fontWeight: '700', fontSize: 11 },
  btnDarkText: { color: '#0f172a', fontWeight: '800', fontSize: 12 },
});
