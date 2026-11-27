import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, StyleSheet, Alert } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
import { apiRequest, uploadBase64Image, uploadCloudAsset } from '../api/client';

export default function InchargeHomeScreen() {
  const [warehouses, setWarehouses] = useState([]);
  const [stockQueue, setStockQueue] = useState([]);
  const [tab, setTab] = useState('facilities'); // 'facilities' | 'stock' | 'gatepass' | 'incident'
  const [whId, setWhId] = useState('');
  const [activityNote, setActivityNote] = useState('');
  const [gatePlate, setGatePlate] = useState('');
  const [gateDriver, setGateDriver] = useState('');
  const [gateCargo, setGateCargo] = useState('');
  const [gateType, setGateType] = useState('inbound');
  const [incCategory, setIncCategory] = useState('WATER_SEEPAGE');
  const [incSeverity, setIncSeverity] = useState('MODERATE');
  const [incDesc, setIncDesc] = useState('');
  const [policeAlert, setPoliceAlert] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scannedText, setScannedText] = useState('');
  const [incAuditNotes, setIncAuditNotes] = useState('');
  const [incCeilingFt, setIncCeilingFt] = useState('');
  const [incPhotoUrl, setIncPhotoUrl] = useState('');
  const [incVideoUrl, setIncVideoUrl] = useState('');
  const [permission, requestPermission] = useCameraPermissions();

  async function refresh() {
    try {
      const [whRes, sqRes] = await Promise.all([
        apiRequest('/api/incharge/assigned-warehouses'),
        apiRequest('/api/incharge/stock-queue'),
      ]);
      const rows = Array.isArray(whRes) ? whRes : [];
      setWarehouses(rows);
      if (rows[0] && !whId) setWhId(String(rows[0].warehouse_id || rows[0].id));
      setStockQueue(Array.isArray(sqRes) ? sqRes : []);
    } catch (err) {
      Alert.alert('Incharge Sync Error', err.message);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function openQrScanner() {
    if (!permission?.granted) {
      const res = await requestPermission();
      if (!res.granted) return Alert.alert('Permission', 'Allow camera access to scan Gate Pass QR codes.');
    }
    setScanning(true);
  }

  async function submitActivityLog() {
    if (!whId || !activityNote.trim()) return Alert.alert('Required', 'Select warehouse ID and enter shift notes.');
    try {
      const res = await apiRequest('/api/incharge/activity-log', {
        method: 'POST',
        body: {
          warehouse_id: parseInt(whId, 10),
          activity_type: 'DOCK_AUDIT',
          notes: activityNote.trim(),
        },
      });
      Alert.alert('Logged!', res.message || 'Inspection shift log sent.');
      setActivityNote('');
    } catch (err) {
      Alert.alert('Log Error', err.message);
    }
  }

  async function submitGatePass() {
    if (!whId || !gatePlate.trim() || !gateDriver.trim()) {
      return Alert.alert('Required', 'Warehouse, Vehicle Plate, and Driver Name are required.');
    }
    try {
      const res = await apiRequest('/api/incharge/gate-pass', {
        method: 'POST',
        body: {
          warehouse_id: parseInt(whId, 10),
          movement_type: gateType,
          vehicle_plate: gatePlate.trim(),
          driver_name: gateDriver.trim(),
          cargo_manifest: gateCargo.trim() || 'Commercial Cargo',
          scanned_units_count: 1,
        },
      });
      Alert.alert('Gate Pass Stamped', res.message || 'Digital pass recorded.');
      setGatePlate('');
      setGateDriver('');
      setGateCargo('');
    } catch (err) {
      Alert.alert('Gate Pass Error', err.message);
    }
  }

  async function verifyStockMovement(logId, decision) {
    try {
      const res = await apiRequest(`/api/incharge/stock/${logId}/verify`, {
        method: 'POST',
        body: {
          action: decision,
          remarks: decision === 'APPROVE' ? 'Dock verified via Mobile App' : 'Discrepancy flagged via Mobile App',
        },
      });
      Alert.alert('Stock Updated', res.message || 'Verification recorded.');
      refresh();
    } catch (err) {
      Alert.alert('Verify Error', err.message);
    }
  }

  async function submitIncident() {
    if (!whId || !incDesc.trim()) return Alert.alert('Required', 'Describe the hazard or security incident.');
    try {
      const res = await apiRequest('/api/incharge/incident-report', {
        method: 'POST',
        body: {
          warehouse_id: parseInt(whId, 10),
          incident_category: incCategory,
          severity: incSeverity,
          description: incDesc.trim(),
          police_alert_dispatched: policeAlert,
        },
      });
      Alert.alert('Incident Dispatched', res.message || 'Alert sent.');
      setIncDesc('');
    } catch (err) {
      Alert.alert('Incident Error', err.message);
    }
  }

  async function snapInspectionPhoto() {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) return Alert.alert('Camera Needed', 'Allow camera access.');
    const shot = await ImagePicker.launchCameraAsync({ quality: 0.5, base64: true });
    if (!shot.canceled && shot.assets?.[0]?.base64) {
      const url = await uploadBase64Image({ filename: 'inspection.jpg', base64: shot.assets[0].base64, category: 'WAREHOUSE_PHOTO' });
      setIncPhotoUrl(url);
      Alert.alert('Photo Uploaded', 'Inspection photo ready to save.');
    }
  }

  async function pickInspectionVideo() {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return Alert.alert('Gallery Needed', 'Allow video gallery access.');
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Videos, quality: 0.7 });
    const asset = !res.canceled && res.assets?.[0];
    if (asset?.uri) {
      const url = await uploadCloudAsset({ uri: asset.uri, filename: asset.fileName || 'inspection.mp4', mimeType: asset.mimeType || 'video/mp4', category: 'WAREHOUSE_VIDEO' });
      setIncVideoUrl(url);
      Alert.alert('Video Uploaded', 'Walkthrough video ready to save.');
    }
  }

  async function submitInspectionMediaAndDetails() {
    if (!whId) return Alert.alert('Select Facility', 'Select an assigned warehouse first.');
    try {
      const res = await apiRequest(`/api/incharge/warehouses/${whId}/media-details`, {
        method: 'POST',
        body: {
          photo_urls: incPhotoUrl ? [incPhotoUrl] : [],
          video_urls: incVideoUrl ? [incVideoUrl] : [],
          clear_ceiling_height_ft: incCeilingFt ? parseFloat(incCeilingFt) : undefined,
          audit_notes: incAuditNotes.trim() || undefined,
        },
      });
      Alert.alert('Saved!', res.message || 'Warehouse inspection media & details updated.');
      setIncPhotoUrl('');
      setIncVideoUrl('');
      setIncAuditNotes('');
      refresh();
    } catch (err) {
      Alert.alert('Update Error', err.message);
    }
  }

  if (scanning) {
    return (
      <View style={{ flex: 1 }}>
        <CameraView
          style={{ flex: 1 }}
          barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
          onBarcodeScanned={({ data }) => {
            setScanning(false);
            setScannedText(data);
            Alert.alert('Gate Pass QR Scanned', data);
          }}
        />
        <TouchableOpacity onPress={() => setScanning(false)} style={[styles.btnDark, { margin: 16 }]}>
          <Text style={styles.btnLight}>Cancel QR Scanner</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.wrap}>
      <View style={styles.tabRow}>
        {[
          ['facilities', 'Sites'],
          ['stock', `Dock (${stockQueue.length})`],
          ['gatepass', 'Gate Pass'],
          ['incident', 'Police/Hazard'],
        ].map(([k, lbl]) => (
          <TouchableOpacity key={k} onPress={() => setTab(k)} style={[styles.tabBtn, tab === k && styles.tabActive]}>
            <Text style={[styles.tabTxt, tab === k && styles.tabTxtActive]}>{lbl}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <TouchableOpacity onPress={openQrScanner} style={styles.btnAmber}>
        <Text style={styles.btnDarkText}>Scan Client Gate Pass / Insurance QR</Text>
      </TouchableOpacity>
      {scannedText ? <View style={styles.card}><Text style={styles.meta}>Last QR: {scannedText}</Text></View> : null}

      {tab === 'facilities' && (
        <View style={{ marginTop: 10 }}>
          <Text style={styles.sec}>Assigned Warehouses ({warehouses.length})</Text>
          {warehouses.map((w) => {
            const wid = w.warehouse_id || w.id;
            return (
              <TouchableOpacity key={wid} onPress={() => setWhId(String(wid))} style={[styles.card, String(wid) === whId && { borderColor: '#f59e0b', borderWidth: 2 }]}>
                <Text style={styles.cardTitle}>#{wid} {w.warehouse_title || w.title}</Text>
                <Text style={styles.meta}>{w.location || w.city} • Audit: {w.physical_audit_status || 'VERIFIED'}</Text>
              </TouchableOpacity>
            );
          })}
          <View style={styles.card}>
            <Text style={styles.sec}>Upload Assigned Site Photo, Video &amp; Details</Text>
            <TextInput value={whId} onChangeText={setWhId} placeholder="Warehouse ID" keyboardType="number-pad" style={styles.input} />
            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
              <TouchableOpacity onPress={snapInspectionPhoto} style={[styles.tabBtn, { backgroundColor: '#0284c7' }]}>
                <Text style={{ color: '#fff', fontSize: 11, fontWeight: '800' }}>{incPhotoUrl ? 'Photo ✓' : '+ Inspection Photo'}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={pickInspectionVideo} style={[styles.tabBtn, { backgroundColor: '#4338ca' }]}>
                <Text style={{ color: '#fff', fontSize: 11, fontWeight: '800' }}>{incVideoUrl ? 'Video ✓' : '+ Walkthrough Video'}</Text>
              </TouchableOpacity>
            </View>
            <TextInput value={incCeilingFt} onChangeText={setIncCeilingFt} placeholder="Verified Ceiling Height (ft)" keyboardType="numeric" style={styles.input} />
            <TextInput value={incAuditNotes} onChangeText={setIncAuditNotes} placeholder="On-site inspection notes & specs..." multiline style={styles.input} />
            <TouchableOpacity onPress={submitInspectionMediaAndDetails} style={[styles.btnDark, { backgroundColor: '#047857', marginBottom: 10 }]}>
              <Text style={styles.btnLight}>Save Inspection Media &amp; Details</Text>
            </TouchableOpacity>
            <Text style={styles.sec}>Shift Inspection Report</Text>
            <TextInput value={activityNote} onChangeText={setActivityNote} placeholder="CCTV, perimeter & humidity check..." multiline style={styles.input} />
            <TouchableOpacity onPress={submitActivityLog} style={styles.btnDark}>
              <Text style={styles.btnLight}>Submit Shift Inspection Log</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {tab === 'stock' && (
        <View style={{ marginTop: 10 }}>
          <Text style={styles.sec}>Pending Client Stock Verifications ({stockQueue.length})</Text>
          {stockQueue.length === 0 ? (
            <View style={styles.card}><Text style={styles.meta}>No pending stock receipts or clearances right now.</Text></View>
          ) : stockQueue.map((item) => (
            <View key={item.log_id} style={styles.card}>
              <Text style={styles.cardTitle}>{item.sku_code} • {item.item_name}</Text>
              <Text style={styles.meta}>{item.action_type} • Qty: {item.quantity_changed} • Client: {item.client_name}</Text>
              <Text style={styles.meta}>Warehouse: {item.warehouse_title}</Text>
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                <TouchableOpacity onPress={() => verifyStockMovement(item.log_id, 'APPROVE')} style={[styles.btnAmber, { flex: 1 }]}>
                  <Text style={styles.btnDarkText}>Verify Receipt</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => verifyStockMovement(item.log_id, 'REJECT')} style={[styles.btnDark, { flex: 0.7, backgroundColor: '#dc2626' }]}>
                  <Text style={styles.btnLight}>Reject</Text>
                </TouchableOpacity>
              </View>
            </View>
          ))}
        </View>
      )}

      {tab === 'gatepass' && (
        <View style={[styles.card, { marginTop: 10 }]}>
          <Text style={styles.sec}>Issue Digital Gate Pass</Text>
          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
            <TouchableOpacity onPress={() => setGateType('inbound')} style={[styles.tabBtn, gateType === 'inbound' && styles.tabActive]}>
              <Text style={[styles.tabTxt, gateType === 'inbound' && styles.tabTxtActive]}>INBOUND</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setGateType('outbound')} style={[styles.tabBtn, gateType === 'outbound' && styles.tabActive]}>
              <Text style={[styles.tabTxt, gateType === 'outbound' && styles.tabTxtActive]}>OUTBOUND</Text>
            </TouchableOpacity>
          </View>
          <TextInput value={whId} onChangeText={setWhId} placeholder="Warehouse ID" keyboardType="number-pad" style={styles.input} />
          <TextInput value={gatePlate} onChangeText={setGatePlate} placeholder="Vehicle Plate (e.g. Ba 2 Kha 4411)" style={styles.input} />
          <TextInput value={gateDriver} onChangeText={setGateDriver} placeholder="Driver Full Name" style={styles.input} />
          <TextInput value={gateCargo} onChangeText={setGateCargo} placeholder="Cargo Manifest Notes" style={styles.input} />
          <TouchableOpacity onPress={submitGatePass} style={styles.btnDark}>
            <Text style={styles.btnLight}>Stamp Digital Gate Pass</Text>
          </TouchableOpacity>
        </View>
      )}

      {tab === 'incident' && (
        <View style={[styles.card, { marginTop: 10 }]}>
          <Text style={styles.sec}>Report Hazard &amp; Emergency Nepal Police Alert</Text>
          <TextInput value={whId} onChangeText={setWhId} placeholder="Warehouse ID" keyboardType="number-pad" style={styles.input} />
          <TextInput value={incCategory} onChangeText={setIncCategory} placeholder="Category (WATER_SEEPAGE, FIRE_ALERT, SEAL_TAMPERING)" style={styles.input} />
          <TextInput value={incSeverity} onChangeText={setIncSeverity} placeholder="Severity (MINOR, MODERATE, CRITICAL)" style={styles.input} />
          <TextInput value={incDesc} onChangeText={setIncDesc} placeholder="Detailed hazard / breach description..." multiline style={styles.input} />
          <TouchableOpacity onPress={() => setPoliceAlert(!policeAlert)} style={[styles.tabBtn, policeAlert && { backgroundColor: '#dc2626' }, { marginBottom: 8 }]}>
            <Text style={[styles.tabTxt, policeAlert && { color: '#fff' }]}>
              {policeAlert ? '1-Click Nepal Police Alert: ON' : 'Include 1-Click Police Alert (Tap to Enable)'}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={submitIncident} style={[styles.btnDark, { backgroundColor: '#b91c1c' }]}>
            <Text style={styles.btnLight}>Dispatch Emergency Incident</Text>
          </TouchableOpacity>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 14, paddingBottom: 40 },
  tabRow: { flexDirection: 'row', gap: 6, marginBottom: 10 },
  tabBtn: { flex: 1, paddingVertical: 8, borderRadius: 10, backgroundColor: '#e2e8f0', alignItems: 'center' },
  tabActive: { backgroundColor: '#0f172a' },
  tabTxt: { fontSize: 11, fontWeight: '700', color: '#475569' },
  tabTxtActive: { color: '#fff' },
  sec: { fontSize: 13, fontWeight: '800', color: '#0f172a', marginBottom: 8 },
  card: { backgroundColor: '#fff', padding: 14, borderRadius: 14, borderWidth: 1, borderColor: '#e2e8f0', marginBottom: 10 },
  cardTitle: { fontSize: 14, fontWeight: '800', color: '#0f172a' },
  meta: { fontSize: 11, color: '#64748b', marginTop: 3 },
  input: { borderWidth: 1, borderColor: '#cbd5e1', borderRadius: 10, padding: 9, marginBottom: 8, fontSize: 12 },
  btnAmber: { backgroundColor: '#f59e0b', padding: 13, borderRadius: 12, alignItems: 'center' },
  btnDark: { backgroundColor: '#0f172a', padding: 12, borderRadius: 10, alignItems: 'center' },
  btnLight: { color: '#fff', fontWeight: '700', fontSize: 12 },
  btnDarkText: { color: '#0f172a', fontWeight: '900', fontSize: 13 },
});
