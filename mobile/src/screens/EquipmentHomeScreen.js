import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, StyleSheet, Alert } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { apiRequest, uploadBase64Image } from '../api/client';

export default function EquipmentHomeScreen({ session }) {
  const isOperatorPin = session?.mode === 'equipment_operator';
  const [fleet, setFleet] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [openOpJobs, setOpenOpJobs] = useState([]);
  const [opMode, setOpMode] = useState('COMMERCIAL_FLEET');
  const [operators, setOperators] = useState([]);
  const [summary, setSummary] = useState({});
  const [eqType, setEqType] = useState('Forklift');
  const [modelName, setModelName] = useState('');
  const [dailyRate, setDailyRate] = useState('8500');
  const [monthlyRate, setMonthlyRate] = useState('165000');
  const [photoUrl, setPhotoUrl] = useState('');

  async function refresh() {
    try {
      if (isOperatorPin) {
        const res = await apiRequest('/api/equipment/operator/active-job');
        setOpMode(res.operator_mode || 'COMMERCIAL_FLEET');
        setJobs(res.assigned_jobs || []);
        setOpenOpJobs(res.open_jobs || []);
      } else {
        const res = await apiRequest('/api/equipment/my-fleet');
        setOpMode(res.operator_type || 'COMMERCIAL_FLEET');
        setFleet(res.equipment || []);
        setJobs(res.jobs || []);
        setOperators(res.operators || []);
        setSummary(res.summary || {});
      }
    } catch (err) {
      Alert.alert('Load Error', err.message);
    }
  }

  useEffect(() => { refresh(); }, []);

  async function snapMachinePhoto() {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) return Alert.alert('Camera Needed', 'Enable camera permission.');
    const shot = await ImagePicker.launchCameraAsync({ quality: 0.5, base64: true });
    if (!shot.canceled && shot.assets?.[0]?.base64) {
      try {
        const url = await uploadBase64Image({ filename: 'equipment.jpg', base64: shot.assets[0].base64 });
        setPhotoUrl(url);
        Alert.alert('Uploaded', 'Machinery photo attached.');
      } catch (err) {
        Alert.alert('Upload Failed', err.message);
      }
    }
  }

  async function registerMachine() {
    if (!modelName.trim()) return Alert.alert('Required', 'Enter machine model name.');
    try {
      const res = await apiRequest('/api/equipment/register', {
        method: 'POST',
        body: {
          equipment_type: eqType,
          model_name: modelName.trim(),
          capacity_ton: 3.0,
          daily_rate_npr: parseFloat(dailyRate) || 8500,
          monthly_rate_npr: parseFloat(monthlyRate) || 165000,
          location_city: 'Kathmandu',
          photo_url: photoUrl || undefined,
        },
      });
      Alert.alert('Registered', res.message);
      setModelName('');
      setPhotoUrl('');
      refresh();
    } catch (err) {
      Alert.alert('Error', err.message);
    }
  }

  async function markJob(jobId, nextStatus) {
    try {
      const url = isOperatorPin
        ? `/api/equipment/operator/jobs/${jobId}/status?status_str=${nextStatus}`
        : `/api/equipment/jobs/${jobId}/status?status_str=${nextStatus}`;
      await apiRequest(url, { method: 'POST' });
      refresh();
    } catch (err) {
      Alert.alert('Error', err.message);
    }
  }

  if (isOperatorPin) {
    const combined = [...jobs, ...openOpJobs];
    return (
      <ScrollView contentContainerStyle={styles.wrap}>
        <View style={styles.kpiCard}>
          <Text style={styles.kpiTitle}>{opMode === 'INDEPENDENT_OPERATOR' ? 'Independent Equipment Operator' : 'Commercial Fleet Equipment Operator'}</Text>
          <Text style={styles.kpiVal}>Assigned Deployments: {combined.length}</Text>
        </View>
        {combined.length === 0 ? (
          <View style={styles.card}><Text style={styles.meta}>No assigned site jobs right now.</Text></View>
        ) : combined.map((j) => (
          <View key={j.id} style={styles.card}>
            <Text style={styles.cardTitle}>{j.job_ref} — {j.equipment_model}</Text>
            <Text style={styles.meta}>{j.site_address} • {j.duration_units} {j.duration_type} • {j.status}</Text>
            <View style={styles.row}>
              {j.status === 'CONFIRMED' && (
                <TouchableOpacity onPress={() => markJob(j.id, 'IN_PROGRESS')} style={styles.btnDark}><Text style={styles.btnLight}>Start Deploy</Text></TouchableOpacity>
              )}
              {j.status === 'IN_PROGRESS' && (
                <TouchableOpacity onPress={() => markJob(j.id, 'COMPLETED')} style={styles.btnAmber}><Text style={styles.btnDarkText}>Mark Completed</Text></TouchableOpacity>
              )}
            </View>
          </View>
        ))}
      </ScrollView>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.wrap}>
      <View style={styles.kpiCard}>
        <Text style={styles.kpiTitle}>Machinery: {summary.total_units || 0} • Operators: {operators.length}</Text>
        <Text style={styles.kpiVal}>Net Payout (90%): Rs. {summary.net_payout_npr || 0}</Text>
        <Text style={[styles.meta, { color: '#fbbf24' }]}>Due to KTM-WDC: Rs. {summary.commission_due_to_kwdc_npr ?? summary.platform_fee_npr ?? 0}</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Add Forklift / Crane / Reach-Stacker</Text>
        <TextInput value={eqType} onChangeText={setEqType} placeholder="Type (Forklift, Mobile Crane...)" style={styles.input} />
        <TextInput value={modelName} onChangeText={setModelName} placeholder="Model Name (e.g. Toyota 3-Ton Forklift)" style={styles.input} />
        <View style={styles.row}>
          <TextInput value={dailyRate} onChangeText={setDailyRate} keyboardType="numeric" placeholder="Daily Rs." style={[styles.input, { flex: 1 }]} />
          <TextInput value={monthlyRate} onChangeText={setMonthlyRate} keyboardType="numeric" placeholder="Monthly Rs." style={[styles.input, { flex: 1 }]} />
        </View>
        <View style={styles.row}>
          <TouchableOpacity onPress={snapMachinePhoto} style={styles.btnDark}><Text style={styles.btnLight}>{photoUrl ? 'Photo Attached ✓' : 'Snap Machine Photo'}</Text></TouchableOpacity>
          <TouchableOpacity onPress={registerMachine} style={styles.btnAmber}><Text style={styles.btnDarkText}>Submit Machinery</Text></TouchableOpacity>
        </View>
      </View>

      <Text style={styles.sec}>Registered Machinery ({fleet.length})</Text>
      {fleet.map((e) => (
        <View key={e.id} style={styles.card}>
          <Text style={styles.cardTitle}>{e.model_name} ({e.equipment_type})</Text>
          <Text style={styles.meta}>{e.is_approved ? 'APPROVED ✓' : 'PENDING ADMIN AUDIT'} • Rs. {e.daily_rate_npr}/day</Text>
        </View>
      ))}

      <Text style={styles.sec}>Rental Jobs ({jobs.length})</Text>
      {jobs.map((j) => (
        <View key={j.id} style={styles.card}>
          <Text style={styles.cardTitle}>{j.job_ref} — {j.equipment_model}</Text>
          <Text style={styles.meta}>{j.site_address} • {j.duration_units} {j.duration_type} • {j.status}</Text>
          <View style={styles.row}>
            {j.status === 'CONFIRMED' && (
              <TouchableOpacity onPress={() => markJob(j.id, 'IN_PROGRESS')} style={styles.btnDark}><Text style={styles.btnLight}>Start Deploy</Text></TouchableOpacity>
            )}
            {j.status === 'IN_PROGRESS' && (
              <TouchableOpacity onPress={() => markJob(j.id, 'COMPLETED')} style={styles.btnAmber}><Text style={styles.btnDarkText}>Mark Completed</Text></TouchableOpacity>
            )}
          </View>
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 14, paddingBottom: 40 },
  kpiCard: { backgroundColor: '#0f172a', padding: 16, borderRadius: 14, marginBottom: 12 },
  kpiTitle: { color: '#94a3b8', fontSize: 12, fontWeight: '700' },
  kpiVal: { color: '#10b981', fontSize: 18, fontWeight: '900', marginTop: 4 },
  sec: { fontSize: 13, fontWeight: '800', color: '#0f172a', marginVertical: 8 },
  card: { backgroundColor: '#fff', padding: 14, borderRadius: 14, borderWidth: 1, borderColor: '#e2e8f0', marginBottom: 10 },
  cardTitle: { fontSize: 14, fontWeight: '800', color: '#0f172a' },
  meta: { fontSize: 11, color: '#64748b', marginTop: 3 },
  input: { borderWidth: 1, borderColor: '#cbd5e1', borderRadius: 10, padding: 9, marginTop: 6, fontSize: 12 },
  row: { flexDirection: 'row', gap: 8, marginTop: 8 },
  btnDark: { flex: 1, backgroundColor: '#0f172a', padding: 10, borderRadius: 10, alignItems: 'center' },
  btnAmber: { flex: 1, backgroundColor: '#f59e0b', padding: 10, borderRadius: 10, alignItems: 'center' },
  btnLight: { color: '#fff', fontWeight: '700', fontSize: 12 },
  btnDarkText: { color: '#0f172a', fontWeight: '800', fontSize: 12 },
});
