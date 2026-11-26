# KTM-WDC React Native Mobile App — Beginner Step-by-Step Testing Guide

This guide is designed for anyone testing a **React Native (Expo)** mobile app for the very first time—no Android Studio or Xcode installation needed!

---

## What Is Inside `mobile/`
The single mobile app (`mobile/`) connects directly to your live **KTM-WDC FastAPI backend** (Vercel + Supabase PostgreSQL) and routes each user to their mobile dashboard:

1. **Fleet Partner & Driver** — Login via account email OR Driver Phone + 4-Digit PIN. Streams **real phone satellite GPS** (`expo-location`), captures **e-POD camera photos**, and verifies Consignee Delivery OTP.
2. **Property Owner** — Uses phone **GPS + Camera** to register godowns, view Occupancy & Realized Yield, and check 10% House Rent TDS net bank deposits.
3. **Commercial Client** — Browses spaces, books Daily/Weekly/Monthly terms, settles Advance Pay, auto-calculates **Google Road KM**, dispatches freight, and checks Heavy Equipment rentals.
4. **Warehouse Incharge** — Native **Camera QR Scanner** to verify Gate Pass / Stock QR codes at warehouse gates + submit inspection/incident logs.
5. **Heavy Equipment Owner** — Registers Forklifts/Cranes/Reach-Stackers with camera photos, tracks site jobs (`CONFIRMED -> IN_PROGRESS -> COMPLETED`), and checks 90/10 net payouts.

---

## Step 1: Install **Expo Go** on Your Phone (Free)
1. On **Android**: Open Google Play Store → search **Expo Go** → Install.
2. On **iPhone**: Open Apple App Store → search **Expo Go** → Install.

---

## Step 2: Install Dependencies & Start Mobile Server on Laptop
Open PowerShell inside your project folder and run:

```powershell
cd c:\Users\Postronix\Desktop\project-warehouse\mobile
npm install
npx expo start
```

> Make sure your phone and laptop are on the **same Wi-Fi network** (or use `npx expo start --tunnel` if on different networks / mobile 4G).

A big **QR code** will appear in your PowerShell terminal:
- **Android**: Open the **Expo Go** app → tap **Scan QR Code** → scan the terminal QR code.
- **iPhone**: Open the normal **iPhone Camera** app → point at the terminal QR code → tap the yellow *"Open in Expo Go"* banner.

---

## Step 3: Point the App to Your Vercel Backend
1. Right on the first **Login Screen** inside the phone app, you will see **"Backend Server URL"**.
2. Enter your deployed Vercel URL (for example: `https://project-kwdc.vercel.app`) and tap **Save**.
   *(Important: First ensure you updated `DATABASE_URL` in Vercel to your **Supabase IPv4 Pooler URI**, otherwise Vercel Web and Mobile won't share the same database!)*

---

## Step 4: Test Web + Mobile Simultaneously (All 5 Entities!)
Keep your laptop browser open to **Web `/admin`** (`admin@kwdc.com.np` / `Admin@123`) while testing on your phone:

1. **Property Owner (Mobile) + Admin (Web)**:
   - On Web: Register/approve Owner KYC + verify via `/admin`.
   - On Phone: Sign in as Property Owner → tap **Pin GPS** → tap **Snap Photo** → submit godown → watch it appear live in `/admin` **Property Audits**!
2. **Heavy Equipment Owner (Mobile or `/equipment` Web) + Admin (Web)**:
   - On Phone: Sign in as Equipment Owner → snap photo of forklift → submit → approve it in Web `/admin` → Client immediately sees it in Equipment Catalog!
3. **Commercial Client (Mobile) + Fleet/Driver (Mobile)**:
   - On Client Phone/Web: Book 1 Freight Dispatch (tap **Google KM** to compute real road distance).
   - Switch to Fleet/Driver → Accept job → assign Driver → log into **Driver PIN Terminal** on phone with mobile + PIN → tap **START TRANSIT & SATELLITE GPS**.
   - Walk/drive outside: you will see `Satellite GPS Lock (±5-15m)` streaming live coordinates onto Web `/client` & `/fleet`!
   - Snap a delivery photo via **Snap Delivery e-POD Photo**, enter Consignee OTP, and tap **COMPLETE DELIVERY**.
4. **Warehouse Incharge (Mobile QR Scanner)**:
   - Sign in as Admin-created Incharge on phone → tap **Open Camera QR Scanner** → scan any Client Gate Pass or Stock QR code displayed on your laptop screen!
