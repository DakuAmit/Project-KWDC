import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, StyleSheet, Alert } from 'react-native';
import { apiRequest } from '../api/client';

export default function ClientHomeScreen({ session }) {
  const [tab, setTab] = useState('catalog'); // catalog | bookings | freight | equipment
  const [warehouses, setWarehouses] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [orders, setOrders] = useState([]);
  const [equipment, setEquipment] = useState([]);
  const [pickup, setPickup] = useState('Balaju Industrial Estate, Kathmandu');
  const [dest, setDest] = useState('Chobhar Dry Port, Kirtipur');
  const [roadKm, setRoadKm] = useState('12');

  async function refreshAll() {
    try {
      const [cat, bks, ords, eq] = await Promise.all([
        apiRequest('/api/warehouses/catalog'),
        apiRequest('/api/warehouses/my-bookings'),
        apiRequest('/api/fleet/client-orders'),
        apiRequest('/api/equipment/catalog'),
      ]);
      setWarehouses(Array.isArray(cat) ? cat : []);
      setBookings(Array.isArray(bks) ? bks : []);
      setOrders(Array.isArray(ords) ? ords : []);
      setEquipment(Array.isArray(eq) ? eq : []);
    } catch (err) {
      Alert.alert('Sync Notice', err.message);
    }
  }

  useEffect(() => { refreshAll(); }, []);

  async function bookStorageSample(wh, durationType = 'DAILY', units = 3) {
    try {
      const res = await apiRequest('/api/warehouses/book', {
        method: 'POST',
        body: {
          warehouse_id: wh.id,
          requested_sqft: Math.min(500, wh.available_sqft || 500),
          booking_duration_type: durationType,
          duration_value: units,
          client_intended_use: 'Mobile App Booking',
        },
      });
      Alert.alert('Booked!', `Booking #${res.booking_id} created (${res.duration_days} days). Settle advance in Bookings tab.`);
      refreshAll();
      setTab('bookings');
    } catch (err) {
      Alert.alert('Booking Error', err.message);
    }
  }

  async function payAdvance(bookingId) {
    try {
      const res = await apiRequest(`/api/warehouses/bookings/${bookingId}/pay-advance`, { method: 'POST' });
      Alert.alert('Activated!', res.message || 'Lease active.');
      refreshAll();
    } catch (err) {
      Alert.alert('Payment Error', err.message);
    }
  }

  async function calcGoogleKm() {
    try {
      const r = await apiRequest(
        `/api/maps/route-distance?origin=${encodeURIComponent(pickup)}&destination=${encodeURIComponent(dest)}`
      );
      setRoadKm(String(r.distance_km));
      Alert.alert('Route Computed', `Distance: ${r.distance_km} km\nETA: ${r.duration_text}\nSource: ${r.source}`);
    } catch (err) {
      Alert.alert('Maps Error', err.message);
    }
  }

  async function dispatchFreight() {
    try {
      const res = await apiRequest('/api/fleet/dispatch-orders', {
        method: 'POST',
        body: {
          movement_type: 'DIRECT_HAUL',
          pickup_address: pickup,
          pickup_contact_name: session.user.full_name || 'Client',
          pickup_contact_phone: session.user.phone_number || '+977-9800000000',
          destination_address: dest,
          consignee_name: 'Receiver Desk',
          consignee_phone: '+977-9841000000',
          cargo_description: 'Commercial Freight (Mobile App)',
          required_vehicle_category: 'mini_truck',
          cargo_weight_kg: 1000,
          estimated_distance_km: parseFloat(roadKm) || 12,
        },
      });
      Alert.alert('Dispatched!', `${res.order_number} broadcast at Rs. ${res.total_fare_npr}`);
      refreshAll();
    } catch (err) {
      Alert.alert('Dispatch Error', err.message);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.wrap}>
      <View style={styles.tabs}>
        {['catalog', 'bookings', 'freight', 'equipment'].map((t) => (
          <TouchableOpacity key={t} onPress={() => setTab(t)} style={[styles.pill, tab === t && styles.pillActive]}>
            <Text style={[styles.pillText, tab === t && styles.pillTextActive]}>{t.toUpperCase()}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'catalog' && warehouses.map((w) => (
        <View key={w.id} style={styles.card}>
          <Text style={styles.cardTitle}>{w.title}</Text>
          <Text style={styles.meta}>{w.municipality}, {w.district} • Avail: {w.available_sqft} sq ft</Text>
          <Text style={styles.price}>Client Tariff: Rs. {w.monthly_rate_per_sqft ?? w.base_rate_per_sqft}/sq ft / month</Text>
          <View style={styles.row}>
            <TouchableOpacity onPress={() => bookStorageSample(w, 'DAILY', 3)} style={styles.btnDark}>
              <Text style={styles.btnLightText}>Book 3 Days</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => bookStorageSample(w, 'MONTHLY', 1)} style={styles.btnAmber}>
              <Text style={styles.btnDarkText}>Book 1 Month</Text>
            </TouchableOpacity>
          </View>
        </View>
      ))}

      {tab === 'bookings' && bookings.map((b) => (
        <View key={b.booking_id} style={styles.card}>
          <Text style={styles.cardTitle}>#{b.booking_id} — {b.warehouse_title}</Text>
          <Text style={styles.meta}>{b.allocated_billed_sqft} sq ft • {b.booking_duration_type} • {b.status}</Text>
          <Text style={styles.meta}>Advance: {b.advance_payment_status} {b.is_gate_frozen ? '• GATE FROZEN' : ''}</Text>
          {b.advance_payment_status !== 'PAID' && (
            <TouchableOpacity onPress={() => payAdvance(b.booking_id)} style={[styles.btnAmber, { marginTop: 8 }]}>
              <Text style={styles.btnDarkText}>Settle Advance &amp; Activate</Text>
            </TouchableOpacity>
          )}
        </View>
      ))}

      {tab === 'freight' && (
        <View>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Book Freight &amp; Auto Road KM</Text>
            <TextInput value={pickup} onChangeText={setPickup} placeholder="Pickup Address" style={styles.input} />
            <TextInput value={dest} onChangeText={setDest} placeholder="Destination Address" style={styles.input} />
            <View style={styles.row}>
              <TextInput value={roadKm} onChangeText={setRoadKm} keyboardType="numeric" style={[styles.input, { flex: 1 }]} />
              <TouchableOpacity onPress={calcGoogleKm} style={styles.btnDark}><Text style={styles.btnLightText}>Google KM</Text></TouchableOpacity>
            </View>
            <TouchableOpacity onPress={dispatchFreight} style={styles.btnAmber}><Text style={styles.btnDarkText}>Dispatch Freight</Text></TouchableOpacity>
          </View>
          {orders.map((o) => (
            <View key={o.id} style={styles.card}>
              <Text style={styles.cardTitle}>{o.order_number} ({o.status})</Text>
              <Text style={styles.meta}>{o.pickup_address} → {o.destination_address}</Text>
              <Text style={styles.price}>Agreed Trip Fare (Zero VAT): Rs. {o.agreed_fare_npr || o.total_fare_npr}</Text>
              <Text style={styles.meta}>Driver Live GPS: {o.live_lat ? `${o.live_lat.toFixed(4)}, ${o.live_lng.toFixed(4)}` : 'Pending Pickup'}</Text>
            </View>
          ))}
        </View>
      )}

      {tab === 'equipment' && equipment.map((e) => (
        <View key={e.id} style={styles.card}>
          <Text style={styles.cardTitle}>{e.model_name} ({e.equipment_type})</Text>
          <Text style={styles.meta}>{e.capacity_ton}T • {e.location_city}</Text>
          <Text style={styles.price}>Rs. {e.daily_rate_npr}/day • Rs. {e.monthly_rate_npr}/month</Text>
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 14, paddingBottom: 40 },
  tabs: { flexDirection: 'row', gap: 6, marginBottom: 12 },
  pill: { flex: 1, paddingVertical: 8, backgroundColor: '#e2e8f0', borderRadius: 10, alignItems: 'center' },
  pillActive: { backgroundColor: '#0f172a' },
  pillText: { fontSize: 10, fontWeight: '800', color: '#475569' },
  pillTextActive: { color: '#fff' },
  card: { backgroundColor: '#fff', padding: 14, borderRadius: 14, borderWidth: 1, borderColor: '#e2e8f0', marginBottom: 10 },
  cardTitle: { fontSize: 14, fontWeight: '800', color: '#0f172a' },
  meta: { fontSize: 11, color: '#64748b', marginTop: 3 },
  price: { fontSize: 12, fontWeight: '800', color: '#047857', marginTop: 4 },
  row: { flexDirection: 'row', gap: 8, marginTop: 8 },
  input: { borderWidth: 1, borderColor: '#cbd5e1', borderRadius: 10, padding: 9, marginTop: 6, fontSize: 12 },
  btnDark: { flex: 1, backgroundColor: '#0f172a', padding: 10, borderRadius: 10, alignItems: 'center' },
  btnAmber: { flex: 1, backgroundColor: '#f59e0b', padding: 10, borderRadius: 10, alignItems: 'center' },
  btnLightText: { color: '#fff', fontWeight: '700', fontSize: 12 },
  btnDarkText: { color: '#0f172a', fontWeight: '800', fontSize: 12 },
});
