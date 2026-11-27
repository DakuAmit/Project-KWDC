import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, StyleSheet, Alert } from 'react-native';
import * as Location from 'expo-location';
import * as ImagePicker from 'expo-image-picker';
import { apiRequest, uploadBase64Image, uploadCloudAsset } from '../api/client';

export default function OwnerHomeScreen() {
  const [tab, setTab] = useState('list'); // 'list' | 'manage' | 'kyc'
  const [title, setTitle] = useState('');
  const [city, setCity] = useState('Kathmandu');
  const [landmark, setLandmark] = useState('');
  const [totalSqft, setTotalSqft] = useState('3000');
  const [rateSqft, setRateSqft] = useState('28');
  const [lat, setLat] = useState(27.7172);
  const [lng, setLng] = useState(85.3240);
  const [photoUrl, setPhotoUrl] = useState('');
  const [videoUrl, setVideoUrl] = useState('');
  const [listings, setListings] = useState([]);
  const [payouts, setPayouts] = useState([]);
  const [kycStatus, setKycStatus] = useState('PENDING');

  // KYC form
  const [citNo, setCitNo] = useState('');
  const [bankName, setBankName] = useState('Nabil Bank');
  const [bankAcc, setBankAcc] = useState('');
  const [citFrontUrl, setCitFrontUrl] = useState('');
  const [holdReason, setHoldReason] = useState('');
  const [revRate, setRevRate] = useState('');

  async function refresh() {
    try {
      const [l, p, k] = await Promise.all([
        apiRequest('/api/warehouses/my-listings'),
        apiRequest('/api/warehouses/my-payouts'),
        apiRequest('/api/auth/kyc-profile'),
      ]);
      setListings(Array.isArray(l) ? l : []);
      setPayouts(Array.isArray(p) ? p : []);
      setKycStatus(k?.kyc_status || 'PENDING');
    } catch {}
  }

  useEffect(() => {
    refresh();
  }, []);

  async function pinMyLocation() {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') return Alert.alert('Permission Needed', 'Grant GPS location permission.');
    const loc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
    setLat(Number(loc.coords.latitude.toFixed(6)));
    setLng(Number(loc.coords.longitude.toFixed(6)));
    Alert.alert('GPS Pinned', `Coords: ${loc.coords.latitude.toFixed(5)}, ${loc.coords.longitude.toFixed(5)}`);
  }

  async function snapFacilityPhoto(onDone, category = 'WAREHOUSE_PHOTO') {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) return Alert.alert('Camera Permission Needed', 'Allow camera access.');
    const shot = await ImagePicker.launchCameraAsync({ quality: 0.5, base64: true });
    if (!shot.canceled && shot.assets?.[0]?.base64) {
      const url = await uploadBase64Image({ filename: 'doc.jpg', base64: shot.assets[0].base64, category });
      onDone(url);
      Alert.alert('Uploaded!', 'Image stored safely in Cloud Storage.');
    }
  }

  async function pickWalkthroughVideo() {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return Alert.alert('Media Permission Needed', 'Allow gallery/video access.');
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Videos, quality: 0.7 });
    const asset = !res.canceled && res.assets?.[0];
    if (asset?.uri) {
      try {
        const url = await uploadCloudAsset({
          uri: asset.uri,
          filename: asset.fileName || 'warehouse_walkthrough.mp4',
          mimeType: asset.mimeType || 'video/mp4',
          category: 'WAREHOUSE_VIDEO',
        });
        setVideoUrl(url);
        Alert.alert('Video Uploaded!', 'Warehouse walkthrough video saved.');
      } catch (err) {
        Alert.alert('Video Upload Error', err.message);
      }
    }
  }

  async function submitProperty() {
    if (!title.trim() || !landmark.trim()) return Alert.alert('Required', 'Title and Landmark are required.');
    try {
      const res = await apiRequest('/api/warehouses/list-space', {
        method: 'POST',
        body: {
          title: title.trim(),
          city: city.trim(),
          neighborhood_landmark: landmark.trim(),
          total_sqft: parseFloat(totalSqft) || 1000,
          monthly_rate_per_sqft: parseFloat(rateSqft) || 25,
          latitude: lat,
          longitude: lng,
          photo_urls: photoUrl ? [photoUrl] : [],
          video_urls: videoUrl ? [videoUrl] : [],
          space_type: 'COMMERCIAL_GODOWN',
          road_access_ft: 20,
          floor_level: 'GROUND',
        },
      });
      Alert.alert('Listed for Inspection', res.message || 'Submitted.');
      setTitle('');
      setLandmark('');
      refresh();
    } catch (err) {
      Alert.alert('Submit Error', err.message);
    }
  }

  async function toggleMaintenanceHold(warehouseId, currentHold) {
    try {
      const res = await apiRequest(`/api/warehouses/${warehouseId}/request-maintenance-hold`, {
        method: 'POST',
        body: {
          is_on_hold: !currentHold,
          hold_reason_note: holdReason.trim() || (currentHold ? 'Maintenance completed' : 'Owner scheduled maintenance'),
        },
      });
      Alert.alert('Hold Status Updated', res.message || 'Updated');
      refresh();
    } catch (err) {
      Alert.alert('Hold Error', err.message);
    }
  }

  async function submitChangeRequest(warehouseId, reqType) {
    try {
      const res = await apiRequest(`/api/warehouses/${warehouseId}/change-request`, {
        method: 'POST',
        body: {
          request_type: reqType,
          requested_rate_per_sqft: reqType === 'RATE_REVISION' ? (parseFloat(revRate) || null) : null,
          reason_note: holdReason.trim() || `Mobile Owner ${reqType}`,
        },
      });
      Alert.alert('Request Sent', res.message || 'Submitted to SuperAdmin.');
      refresh();
    } catch (err) {
      Alert.alert('Request Error', err.message);
    }
  }

  async function addMediaToExistingWarehouse(warehouseId, isVideo) {
    try {
      let mediaUrl = '';
      if (isVideo) {
        const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
        if (!perm.granted) return Alert.alert('Gallery Needed', 'Allow video access.');
        const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Videos, quality: 0.7 });
        const asset = !res.canceled && res.assets?.[0];
        if (!asset?.uri) return;
        mediaUrl = await uploadCloudAsset({ uri: asset.uri, filename: asset.fileName || 'warehouse.mp4', mimeType: asset.mimeType || 'video/mp4', category: 'WAREHOUSE_VIDEO' });
      } else {
        const perm = await ImagePicker.requestCameraPermissionsAsync();
        if (!perm.granted) return Alert.alert('Camera Needed', 'Allow camera access.');
        const shot = await ImagePicker.launchCameraAsync({ quality: 0.5, base64: true });
        if (shot.canceled || !shot.assets?.[0]?.base64) return;
        mediaUrl = await uploadBase64Image({ filename: 'warehouse.jpg', base64: shot.assets[0].base64, category: 'WAREHOUSE_PHOTO' });
      }
      const saved = await apiRequest(`/api/warehouses/${warehouseId}/media`, {
        method: 'POST',
        body: {
          photo_urls: !isVideo ? [mediaUrl] : [],
          video_urls: isVideo ? [mediaUrl] : [],
          caption: holdReason.trim() || 'Uploaded from Mobile Owner App',
        },
      });
      Alert.alert('Media Added!', saved.message || 'Saved to warehouse listing.');
      refresh();
    } catch (err) {
      Alert.alert('Upload Error', err.message);
    }
  }

  async function submitOwnerKyc() {
    if (!citNo.trim() || !bankAcc.trim()) return Alert.alert('Required', 'Enter Citizenship No & Bank Account Number.');
    try {
      const res = await apiRequest('/api/auth/submit-kyc', {
        method: 'POST',
        body: {
          citizenship_number: citNo.trim(),
          citizenship_front_url: citFrontUrl || undefined,
          bank_name: bankName.trim(),
          bank_account_number: bankAcc.trim(),
        },
      });
      Alert.alert('KYC Submitted', res.message || 'Sent for SuperAdmin review.');
      refresh();
    } catch (err) {
      Alert.alert('KYC Error', err.message);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.wrap}>
      <View style={styles.tabRow}>
        {[['list', 'List Space'], ['manage', `Spaces (${listings.length})`], ['kyc', `KYC (${kycStatus})`]].map(([k, lbl]) => (
          <TouchableOpacity key={k} onPress={() => setTab(k)} style={[styles.tabBtn, tab === k && styles.tabActive]}>
            <Text style={[styles.tabTxt, tab === k && styles.tabTxtActive]}>{lbl}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'list' && (
        <View style={styles.card}>
          <Text style={styles.sec}>Register Warehouse Space (KYC: {kycStatus})</Text>
          <TextInput value={title} onChangeText={setTitle} placeholder="Facility Title (e.g. Balaju Godown)" style={styles.input} />
          <TextInput value={city} onChangeText={setCity} placeholder="City" style={styles.input} />
          <TextInput value={landmark} onChangeText={setLandmark} placeholder="Landmark / Chowk" style={styles.input} />
          <View style={styles.row}>
            <TextInput value={totalSqft} onChangeText={setTotalSqft} placeholder="Sq Ft" keyboardType="numeric" style={[styles.input, { flex: 1 }]} />
            <TextInput value={rateSqft} onChangeText={setRateSqft} placeholder="Rs/SqFt" keyboardType="numeric" style={[styles.input, { flex: 1 }]} />
          </View>
          <View style={styles.row}>
            <TouchableOpacity onPress={pinMyLocation} style={[styles.btnDark, { flex: 1 }]}><Text style={styles.btnLight}>Pin GPS ({lat.toFixed(3)}, {lng.toFixed(3)})</Text></TouchableOpacity>
            <TouchableOpacity onPress={() => snapFacilityPhoto(setPhotoUrl, 'WAREHOUSE_PHOTO')} style={[styles.btnDark, { flex: 1 }]}><Text style={styles.btnLight}>{photoUrl ? 'Photo ✓' : 'Camera Photo'}</Text></TouchableOpacity>
            <TouchableOpacity onPress={pickWalkthroughVideo} style={[styles.btnDark, { flex: 1, backgroundColor: '#4338ca' }]}><Text style={styles.btnLight}>{videoUrl ? 'Video ✓' : 'Upload Video'}</Text></TouchableOpacity>
          </View>
          <TouchableOpacity onPress={submitProperty} style={styles.btnAmber}><Text style={styles.btnDarkText}>Submit for Incharge Audit</Text></TouchableOpacity>
        </View>
      )}

      {tab === 'manage' && (
        <View>
          <View style={styles.card}>
            <TextInput value={holdReason} onChangeText={setHoldReason} placeholder="Maintenance / Delisting Reason Note" style={styles.input} />
            <TextInput value={revRate} onChangeText={setRevRate} placeholder="New Proposed Rate (Rs./sq ft for revision)" keyboardType="numeric" style={styles.input} />
          </View>
          {listings.map((w) => (
            <View key={w.id} style={styles.card}>
              <Text style={styles.cardTitle}>{w.title} ({w.is_approved ? 'LIVE' : 'PENDING'})</Text>
              <Text style={styles.meta}>{w.available_sqft}/{w.total_sqft} sq ft • Rs. {w.monthly_rate_per_sqft}/sq ft • Hold: {w.is_on_hold ? 'ON HOLD' : 'ACTIVE'}</Text>
              <View style={[styles.row, { marginTop: 8 }]}>
                <TouchableOpacity onPress={() => addMediaToExistingWarehouse(w.id, false)} style={[styles.btnDark, { flex: 1, backgroundColor: '#0284c7' }]}>
                  <Text style={styles.btnLight}>+ Photo</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => addMediaToExistingWarehouse(w.id, true)} style={[styles.btnDark, { flex: 1, backgroundColor: '#4338ca' }]}>
                  <Text style={styles.btnLight}>+ Video</Text>
                </TouchableOpacity>
              </View>
              <View style={[styles.row, { marginTop: 4 }]}>
                <TouchableOpacity onPress={() => toggleMaintenanceHold(w.id, w.is_on_hold)} style={[styles.btnDark, { flex: 1 }]}>
                  <Text style={styles.btnLight}>{w.is_on_hold ? 'Release Hold' : 'Maintenance Hold'}</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => submitChangeRequest(w.id, 'DELISTING_15_DAYS')} style={[styles.btnDark, { flex: 1, backgroundColor: '#b91c1c' }]}>
                  <Text style={styles.btnLight}>15d Delist</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => submitChangeRequest(w.id, 'RATE_REVISION')} style={[styles.btnAmber, { flex: 1, marginTop: 0 }]}>
                  <Text style={styles.btnDarkText}>Rate Rev</Text>
                </TouchableOpacity>
              </View>
            </View>
          ))}
          <Text style={styles.sec}>90% Owner Payout Ledger ({payouts.length})</Text>
          {payouts.map((p) => (
            <View key={p.booking_id || p.id} style={styles.card}>
              <Text style={styles.cardTitle}>{p.warehouse_title} • Rs. {p.owner_payout_npr}</Text>
              <Text style={styles.meta}>Status: {p.payout_status} • SqFt: {p.leased_sqft}</Text>
            </View>
          ))}
        </View>
      )}

      {tab === 'kyc' && (
        <View style={styles.card}>
          <Text style={styles.sec}>Citizenship &amp; Bank KYC ({kycStatus})</Text>
          <TextInput value={citNo} onChangeText={setCitNo} placeholder="Citizenship Number (e.g. 27-01-74-01122)" style={styles.input} />
          <TextInput value={bankName} onChangeText={setBankName} placeholder="Nepal Commercial Bank Name" style={styles.input} />
          <TextInput value={bankAcc} onChangeText={setBankAcc} placeholder="Bank Account Number (for 90% Payouts)" style={styles.input} />
          <TouchableOpacity onPress={() => snapFacilityPhoto(setCitFrontUrl)} style={styles.btnDark}>
            <Text style={styles.btnLight}>{citFrontUrl ? 'Citizenship Photo Uploaded ✓' : 'Snap Citizenship Photo'}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={submitOwnerKyc} style={styles.btnAmber}>
            <Text style={styles.btnDarkText}>Submit Owner KYC to SuperAdmin</Text>
          </TouchableOpacity>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 14, paddingBottom: 40 },
  tabRow: { flexDirection: 'row', gap: 6, marginBottom: 12 },
  tabBtn: { flex: 1, paddingVertical: 8, borderRadius: 10, backgroundColor: '#e2e8f0', alignItems: 'center' },
  tabActive: { backgroundColor: '#0f172a' },
  tabTxt: { fontSize: 11, fontWeight: '700', color: '#475569' },
  tabTxtActive: { color: '#fff' },
  sec: { fontSize: 14, fontWeight: '800', color: '#0f172a', marginBottom: 8 },
  card: { backgroundColor: '#fff', padding: 14, borderRadius: 14, borderWidth: 1, borderColor: '#e2e8f0', marginBottom: 12 },
  cardTitle: { fontSize: 14, fontWeight: '800', color: '#0f172a' },
  meta: { fontSize: 11, color: '#64748b', marginTop: 3 },
  input: { borderWidth: 1, borderColor: '#cbd5e1', borderRadius: 10, padding: 10, fontSize: 13, marginBottom: 10 },
  row: { flexDirection: 'row', gap: 6 },
  btnDark: { backgroundColor: '#0f172a', padding: 11, borderRadius: 10, alignItems: 'center', marginBottom: 8 },
  btnAmber: { backgroundColor: '#f59e0b', padding: 12, borderRadius: 10, alignItems: 'center', marginTop: 4 },
  btnLight: { color: '#fff', fontWeight: '700', fontSize: 11 },
  btnDarkText: { color: '#0f172a', fontWeight: '900', fontSize: 13 },
});
