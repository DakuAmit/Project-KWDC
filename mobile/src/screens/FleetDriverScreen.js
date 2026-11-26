import React, { useEffect, useRef, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, StyleSheet, Alert } from 'react-native';
import * as Location from 'expo-location';
import * as ImagePicker from 'expo-image-picker';
import { apiRequest, uploadBase64Image } from '../api/client';

export default function FleetDriverScreen({ session }) {
  const isDriverPinMode = session.mode === 'driver';
  const [driverMode, setDriverMode] = useState('COMMERCIAL_3PL');
  const [vehicleCategory, setVehicleCategory] = useState(null);
  const [activeTrip, setActiveTrip] = useState(null);
  const [openDriverJobs, setOpenDriverJobs] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [earnings, setEarnings] = useState(null);
  const [gpsStatus, setGpsStatus] = useState('Idle');
  const [otpInput, setOtpInput] = useState('');
  const [bidFare, setBidFare] = useState('');
  const [epodPhotoUrl, setEpodPhotoUrl] = useState('');
  const [fleetRoster, setFleetRoster] = useState({ vehicles: [], drivers: [] });
  const [fleetBidFare, setFleetBidFare] = useState('');
  const watchSubRef = useRef(null);

  async function refresh() {
    try {
      if (isDriverPinMode) {
        const res = await apiRequest('/api/fleet/driver/active-trip');
        const mode = res.driver_mode || 'COMMERCIAL_3PL';
        setDriverMode(mode);
        setVehicleCategory(res.vehicle_category || null);
        setActiveTrip(res.has_active_trip ? (res.trip || res.active_trip) : null);
        if (mode === 'INDEPENDENT_OWNER') {
          const openRes = await apiRequest('/api/fleet/driver/available-jobs');
          setOpenDriverJobs(Array.isArray(openRes.jobs) ? openRes.jobs : []);
        } else {
          setOpenDriverJobs([]);
        }
      } else {
        const [list, earn, roster] = await Promise.all([
          apiRequest('/api/fleet/dispatch-orders'),
          apiRequest('/api/fleet/earnings'),
          apiRequest('/api/fleet/my-fleet'),
        ]);
        setJobs(Array.isArray(list) ? list : []);
        setEarnings(earn || null);
        setFleetRoster(roster || { vehicles: [], drivers: [] });
      }
    } catch (err) {
      Alert.alert('Sync Notice', err.message);
    }
  }

  useEffect(() => {
    refresh();
    return () => {
      watchSubRef.current?.remove?.();
    };
  }, []);

  async function startSatelliteGps(orderId) {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Location Required', 'Grant GPS location permission so clients can track live transit.');
      return;
    }
    watchSubRef.current?.remove?.();
    watchSubRef.current = await Location.watchPositionAsync(
      { accuracy: Location.Accuracy.High, timeInterval: 5000, distanceInterval: 10 },
      async (loc) => {
        const acc = Math.round(loc.coords.accuracy || 0);
        setGpsStatus(`Satellite GPS Lock: ${loc.coords.latitude.toFixed(5)}, ${loc.coords.longitude.toFixed(5)} (±${acc}m)`);
        try {
          await apiRequest(`/api/fleet/driver/trips/${orderId}/location`, {
            method: 'POST',
            body: { latitude: loc.coords.latitude, longitude: loc.coords.longitude, heading: loc.coords.heading || 0 },
          });
        } catch {}
      }
    );
  }

  async function startTrip() {
    if (!activeTrip) return;
    try {
      await apiRequest(`/api/fleet/driver/trips/${activeTrip.order_id}/start`, { method: 'POST' });
      await startSatelliteGps(activeTrip.order_id);
      Alert.alert('Transit Started', 'Live phone GPS telemetry is now broadcasting.');
      refresh();
    } catch (err) {
      Alert.alert('Start Failed', err.message);
    }
  }

  async function captureEpodPhoto() {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) return Alert.alert('Camera Needed', 'Enable camera permission.');
    const shot = await ImagePicker.launchCameraAsync({ quality: 0.5, base64: true });
    if (!shot.canceled && shot.assets?.[0]?.base64) {
      const url = await uploadBase64Image({ filename: 'epod.jpg', base64: shot.assets[0].base64 });
      setEpodPhotoUrl(url);
      Alert.alert('e-POD Captured', 'Delivery proof photo uploaded.');
    }
  }

  async function completeDelivery() {
    if (!activeTrip) return;
    try {
      await apiRequest(`/api/fleet/driver/trips/${activeTrip.order_id}/complete`, {
        method: 'POST',
        body: {
          delivery_otp: otpInput.trim() || undefined,
          proof_photo_url: epodPhotoUrl || undefined,
          consignee_remarks: 'Delivered safely via Mobile Cab App',
        },
      });
      watchSubRef.current?.remove?.();
      setGpsStatus('Idle');
      Alert.alert('Delivered!', 'Trip completed & e-POD recorded.');
      refresh();
    } catch (err) {
      Alert.alert('Completion Error', err.message);
    }
  }

  async function completeStop(orderId, stopId) {
    try {
      await apiRequest(`/api/fleet/driver/trips/${orderId}/stops/${stopId}/complete`, { method: 'POST' });
      refresh();
    } catch (err) {
      Alert.alert('Stop Error', err.message);
    }
  }

  async function driverAcceptOpenJob(orderId) {
    try {
      const res = await apiRequest(`/api/fleet/driver/jobs/${orderId}/accept`, { method: 'POST' });
      Alert.alert('Trip Accepted', res.message || 'Claimed!');
      refresh();
    } catch (err) {
      Alert.alert('Accept Error', err.message);
    }
  }

  async function driverBidOpenJob(orderId, currentFare) {
    const fare = parseFloat(bidFare) || currentFare;
    try {
      const res = await apiRequest(`/api/fleet/driver/jobs/${orderId}/counter-offer`, {
        method: 'POST',
        body: { offered_fare_npr: fare, counter_note: 'Mobile Driver App Bid' },
      });
      Alert.alert('Bid Sent', res.message || 'Counter-offer submitted.');
      setBidFare('');
      refresh();
    } catch (err) {
      Alert.alert('Bid Error', err.message);
    }
  }

  async function driverDeclineOpenJob(orderId) {
    try {
      await apiRequest(`/api/fleet/driver/jobs/${orderId}/decline`, { method: 'POST' });
      refresh();
    } catch {}
  }

  async function acceptFleetJob(id) {
    try {
      const res = await apiRequest(`/api/fleet/dispatch-orders/${id}/accept`, { method: 'POST' });
      Alert.alert('Accepted', res.message || 'Freight order claimed!');
      refresh();
    } catch (err) {
      Alert.alert('Error', err.message);
    }
  }

  async function counterOfferFleetJob(id, currentFare) {
    const fare = parseFloat(fleetBidFare) || currentFare;
    try {
      const res = await apiRequest(`/api/fleet/dispatch-orders/${id}/counter-offer`, {
        method: 'POST',
        body: { offered_fare_npr: fare, counter_note: 'Mobile Fleet Manager Counter-Offer' },
      });
      Alert.alert('Counter-Offer Sent', res.message || 'Bid submitted to Client!');
      setFleetBidFare('');
      refresh();
    } catch (err) {
      Alert.alert('Counter-Offer Error', err.message);
    }
  }

  async function breakdownReassignOrder(orderId) {
    const standbyV = (fleetRoster.vehicles || [])[0];
    const standbyD = (fleetRoster.drivers || [])[0];
    if (!standbyV || !standbyD) {
      return Alert.alert('Standby Needed', 'Register a standby vehicle and driver on your Fleet roster first.');
    }
    try {
      const res = await apiRequest(`/api/fleet/orders/${orderId}/reassign`, {
        method: 'POST',
        body: {
          new_vehicle_id: standbyV.id,
          new_driver_id: standbyD.id,
          breakdown_reason: 'Mobile Rescue Standby Handover',
        },
      });
      Alert.alert('Rescue Dispatched', res.message || 'Order reassigned safely.');
      refresh();
    } catch (err) {
      Alert.alert('Reassign Error', err.message);
    }
  }

  if (isDriverPinMode) {
    const isIndependent = driverMode === 'INDEPENDENT_OWNER';
    const tripStatusUpper = String(activeTrip?.status || '').toUpperCase();
    return (
      <ScrollView contentContainerStyle={styles.wrap}>
        <View style={styles.gpsBox}>
          <Text style={styles.gpsTitle}>
            {isIndependent ? 'Independent Owner-Driver' : 'Logistics Fleet Driver'} {vehicleCategory ? `(${vehicleCategory})` : ''}
          </Text>
          <Text style={styles.gpsText}>{gpsStatus}</Text>
        </View>

        {!activeTrip ? (
          <View>
            <View style={styles.card}>
              <Text style={styles.cardTitle}>No Assigned Active Trip</Text>
              <Text style={styles.meta}>
                {isIndependent
                  ? 'Accept or counter-offer matching open loads below.'
                  : 'Wait for your Logistics Fleet Manager to assign a run to your vehicle.'}
              </Text>
              <TouchableOpacity onPress={refresh} style={[styles.btnDark, { marginTop: 10 }]}>
                <Text style={styles.btnLight}>Refresh Jobs</Text>
              </TouchableOpacity>
            </View>

            {isIndependent && (
              <View>
                <Text style={styles.sec}>Matching Available Loads ({openDriverJobs.length})</Text>
                {openDriverJobs.map((j) => (
                  <View key={j.id} style={styles.card}>
                    <Text style={styles.cardTitle}>{j.order_number} • Rs. {j.agreed_fare_npr}</Text>
                    <Text style={styles.meta}>{j.cargo_description}</Text>
                    <Text style={styles.meta}>{j.pickup_address} → {j.delivery_address} ({j.total_distance_km} KM)</Text>
                    <Text style={styles.price}>Commission: Rs. {j.kwdc_commission_npr} • Net Retained: Rs. {j.net_retained_npr}</Text>
                    <TextInput value={bidFare} onChangeText={setBidFare} placeholder={`Counter Fare (NPR) e.g. ${j.agreed_fare_npr}`} keyboardType="numeric" style={styles.input} />
                    <View style={{ flexDirection: 'row', gap: 6, marginTop: 8 }}>
                      <TouchableOpacity onPress={() => driverAcceptOpenJob(j.id)} style={[styles.btnAmber, { flex: 1 }]}><Text style={styles.btnDarkText}>Accept</Text></TouchableOpacity>
                      <TouchableOpacity onPress={() => driverBidOpenJob(j.id, j.agreed_fare_npr)} style={[styles.btnDark, { flex: 1 }]}><Text style={styles.btnLight}>Raise Fare</Text></TouchableOpacity>
                      <TouchableOpacity onPress={() => driverDeclineOpenJob(j.id)} style={[styles.btnDark, { flex: 0.7, backgroundColor: '#475569' }]}><Text style={styles.btnLight}>Decline</Text></TouchableOpacity>
                    </View>
                  </View>
                ))}
              </View>
            )}
          </View>
        ) : (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>{activeTrip.order_number} • {tripStatusUpper}</Text>
            <Text style={styles.meta}>Cargo: {activeTrip.cargo_description}</Text>
            <Text style={styles.meta}>Pickup: {activeTrip.pickup_address}</Text>
            <Text style={styles.meta}>Drop: {activeTrip.destination_address} ({activeTrip.consignee_name})</Text>
            <Text style={styles.price}>Agreed Trip Fare (COD): Rs. {activeTrip.agreed_fare_npr || 0}</Text>
            <Text style={styles.meta}>Delivery OTP: {activeTrip.delivery_otp || 'Generated on Start'}</Text>
            {Array.isArray(activeTrip.stops) && activeTrip.stops.length > 1 && (
              <View style={{ marginTop: 8, paddingTop: 6, borderTopWidth: 1, borderColor: '#e2e8f0' }}>
                <Text style={styles.sec}>Multi-Drop Stops ({activeTrip.stops.length})</Text>
                {activeTrip.stops.map((st) => (
                  <View key={st.id} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
                    <Text style={styles.meta}>#{st.stop_sequence}: {st.destination_address}</Text>
                    {st.is_completed ? (
                      <Text style={{ fontSize: 10, color: '#047857', fontWeight: '800' }}>Done ✓</Text>
                    ) : (
                      <TouchableOpacity onPress={() => completeStop(activeTrip.order_id, st.id)} style={{ backgroundColor: '#0f172a', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}>
                        <Text style={{ color: '#fff', fontSize: 10, fontWeight: '700' }}>Complete</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                ))}
              </View>
            )}

            {tripStatusUpper !== 'IN_TRANSIT' ? (
              <TouchableOpacity onPress={startTrip} style={[styles.btnAmber, { marginTop: 12 }]}>
                <Text style={styles.btnDarkText}>START TRANSIT &amp; SATELLITE GPS</Text>
              </TouchableOpacity>
            ) : (
              <View style={{ marginTop: 12 }}>
                <TouchableOpacity onPress={() => startSatelliteGps(activeTrip.order_id)} style={styles.btnDark}>
                  <Text style={styles.btnLight}>Resume Live Satellite GPS</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={captureEpodPhoto} style={[styles.btnDark, { marginTop: 8 }]}>
                  <Text style={styles.btnLight}>{epodPhotoUrl ? 'e-POD Photo Uploaded ✓' : 'Snap Delivery e-POD Photo'}</Text>
                </TouchableOpacity>
                <TextInput value={otpInput} onChangeText={setOtpInput} placeholder="Enter Consignee 4-Digit OTP" keyboardType="number-pad" style={styles.input} />
                <TouchableOpacity onPress={completeDelivery} style={[styles.btnAmber, { marginTop: 8 }]}>
                  <Text style={styles.btnDarkText}>COMPLETE DELIVERY &amp; SUBMIT e-POD</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        )}
      </ScrollView>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.wrap}>
      {earnings && (
        <View style={styles.gpsBox}>
          <Text style={styles.gpsTitle}>Total Earnings: Rs. {earnings.total_gross_npr || 0} | Net: Rs. {earnings.net_fleet_earnings_npr || 0}</Text>
          <Text style={styles.gpsText}>Platform Commission Due to KTM-WDC: Rs. {earnings.commission_due_to_kwdc_npr || 0}</Text>
        </View>
      )}
      <Text style={styles.sec}>Live Freight Load Board ({jobs.length})</Text>
      {jobs.length === 0 ? (
        <View style={styles.card}><Text style={styles.meta}>No open freight jobs right now.</Text></View>
      ) : jobs.map((j) => {
        const stUpper = String(j.status || '').toUpperCase();
        const fare = j.agreed_fare_npr || j.client_offered_fare_npr || j.gross_fare_npr || 0;
        return (
          <View key={j.id} style={styles.card}>
            <Text style={styles.cardTitle}>{j.order_number} ({stUpper})</Text>
            <Text style={styles.meta}>{j.pickup_address} → {j.destination_address}</Text>
            <Text style={styles.price}>Trip Fare: Rs. {fare} (Due to KTM-WDC: Rs. {j.kwdc_margin_npr || 0} • Net: Rs. {j.net_fleet_earnings_npr || 0})</Text>
            {stUpper === 'REQUESTED' && (
              <View style={{ marginTop: 8 }}>
                <TextInput value={fleetBidFare} onChangeText={setFleetBidFare} placeholder={`Counter Fare NPR (e.g. ${fare})`} keyboardType="numeric" style={styles.input} />
                <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                  <TouchableOpacity onPress={() => acceptFleetJob(j.id)} style={[styles.btnAmber, { flex: 1 }]}>
                    <Text style={styles.btnDarkText}>Accept Rs. {fare}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => counterOfferFleetJob(j.id, fare)} style={[styles.btnDark, { flex: 1 }]}>
                    <Text style={styles.btnLight}>Counter Bid</Text>
                  </TouchableOpacity>
                </View>
              </View>
            )}
            {(stUpper === 'ACCEPTED' || stUpper === 'IN_TRANSIT') && (
              <TouchableOpacity onPress={() => breakdownReassignOrder(j.id)} style={[styles.btnDark, { marginTop: 8, backgroundColor: '#b91c1c' }]}>
                <Text style={styles.btnLight}>Rescue / Reassign Standby Unit</Text>
              </TouchableOpacity>
            )}
          </View>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 14, paddingBottom: 40 },
  gpsBox: { backgroundColor: '#0f172a', padding: 14, borderRadius: 14, marginBottom: 12 },
  gpsTitle: { color: '#f59e0b', fontWeight: '800', fontSize: 12 },
  gpsText: { color: '#34d399', fontSize: 12, marginTop: 4, fontWeight: '700' },
  sec: { fontSize: 13, fontWeight: '800', color: '#0f172a', marginBottom: 8 },
  card: { backgroundColor: '#fff', padding: 14, borderRadius: 14, borderWidth: 1, borderColor: '#e2e8f0', marginBottom: 10 },
  cardTitle: { fontSize: 14, fontWeight: '800', color: '#0f172a' },
  meta: { fontSize: 11, color: '#64748b', marginTop: 3 },
  price: { fontSize: 12, fontWeight: '800', color: '#047857', marginTop: 4 },
  input: { borderWidth: 1, borderColor: '#cbd5e1', borderRadius: 10, padding: 9, marginTop: 8, fontSize: 12 },
  btnDark: { backgroundColor: '#0f172a', padding: 11, borderRadius: 10, alignItems: 'center' },
  btnAmber: { backgroundColor: '#f59e0b', padding: 12, borderRadius: 10, alignItems: 'center' },
  btnLight: { color: '#fff', fontWeight: '700', fontSize: 12 },
  btnDarkText: { color: '#0f172a', fontWeight: '900', fontSize: 12 },
});
