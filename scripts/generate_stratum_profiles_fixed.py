"""
STRATUM OMNIS Entity Profile Generator - FIXED VERSION
Fixes: UNIQUE constraint on identities.id by using full UUID
"""
import sqlite3
import uuid
import json
import random
import os
from datetime import datetime, timedelta

# ── Constants ─────────────────────────────────────────────────
DB_PATH = 'backend/database/julius.db'
TARGET_PROFILES = 100000
NOW = datetime.utcnow().isoformat()

# ── Reference Data ─────────────────────────────────────────────
PLATFORMS = [
    'email', 'twitter', 'linkedin', 'github', 'facebook',
    'instagram', 'telegram', 'slack', 'phone', 'darkweb',
    'network_scan', 'osint', 'telco', 'upi', 'physical'
]
INDIAN_CITIES = [
    'Mumbai', 'Delhi', 'Bangalore', 'Hyderabad', 'Chennai',
    'Kolkata', 'Pune', 'Ahmedabad', 'Jaipur', 'Surat',
    'Lucknow', 'Kanpur', 'Nagpur', 'Indore', 'Thane',
    'Bhopal', 'Visakhapatnam', 'Patna', 'Vadodara', 'Ghaziabad'
]
STATES = [
    'Maharashtra', 'Delhi', 'Karnataka', 'Telangana', 'Tamil Nadu',
    'West Bengal', 'Gujarat', 'Rajasthan', 'Uttar Pradesh', 'Madhya Pradesh'
]
OCCUPATIONS = [
    'Software Engineer', 'Business Analyst', 'Marketing Manager',
    'Financial Analyst', 'Product Manager', 'Data Scientist',
    'Operations Manager', 'Sales Executive', 'HR Manager',
    'Entrepreneur', 'Student', 'Teacher', 'Doctor', 'Lawyer',
    'Accountant', 'Consultant', 'Architect', 'Designer',
    'Journalist', 'Government Employee'
]
INCOME_BANDS = ['A+', 'A', 'B+', 'B', 'C+', 'C', 'D']
DEVICE_TYPES = ['Android', 'iOS', 'Windows', 'MacOS', 'Linux']
TELCOS = ['Jio', 'Airtel', 'Vi', 'BSNL']
SPENDING_CATEGORIES = [
    'food_delivery', 'ecommerce', 'travel', 'entertainment',
    'utilities', 'healthcare', 'education', 'fitness',
    'fashion', 'electronics', 'groceries', 'dining'
]
BEHAVIORAL_PATTERNS = [
    'early_adopter', 'price_sensitive', 'brand_loyal',
    'impulse_buyer', 'researcher', 'social_influencer',
    'risk_averse', 'premium_seeker', 'deal_hunter',
    'routine_buyer', 'seasonal_buyer', 'subscription_prone'
]
RISK_LEVELS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
PREDICTION_DOMAINS = [
    'purchase', 'financial', 'mobility', 'digital', 'social'
]
EVENT_TYPES = [
    'repo_rate_change', 'election_announcement', 'natural_disaster',
    'market_crash', 'new_product_launch', 'policy_change',
    'inflation_spike', 'employment_data', 'geopolitical_tension',
    'pandemic_alert', 'festival_season', 'budget_announcement'
]
FIRST_NAMES = [
    'Aarav', 'Vivaan', 'Aditya', 'Vihaan', 'Arjun', 'Sai', 'Reyansh',
    'Ayaan', 'Krishna', 'Ishaan', 'Ananya', 'Diya', 'Priya', 'Shreya',
    'Riya', 'Kavya', 'Pooja', 'Neha', 'Swati', 'Anjali', 'Rahul',
    'Rohit', 'Amit', 'Vijay', 'Suresh', 'Ramesh', 'Deepak', 'Nikhil',
    'Vishal', 'Sandeep', 'Meera', 'Sunita', 'Rekha', 'Geeta', 'Seema',
    'Radha', 'Uma', 'Sita', 'Lakshmi', 'Parvati', 'Mohan', 'Sohan',
    'Rohan', 'Kiran', 'Tarun', 'Varun', 'Arun', 'Karun', 'Rajan',
    'Sajan', 'Aryan', 'Ryan', 'Nayan', 'Gyan', 'Dhyan', 'Mayan',
    'Pranav', 'Tanav', 'Manav', 'Arnav', 'Gaurav', 'Saurav', 'Sourav'
]
LAST_NAMES = [
    'Sharma', 'Verma', 'Patel', 'Singh', 'Kumar', 'Gupta', 'Joshi',
    'Mehta', 'Shah', 'Rao', 'Reddy', 'Nair', 'Pillai', 'Iyer', 'Menon',
    'Malhotra', 'Kapoor', 'Khanna', 'Bose', 'Chatterjee', 'Banerjee',
    'Das', 'Roy', 'Sen', 'Mukherjee', 'Ghosh', 'Chakraborty', 'Dutta',
    'Mishra', 'Pandey', 'Tiwari', 'Dubey', 'Tripathi', 'Srivastava',
    'Awasthi', 'Chaudhary', 'Yadav', 'Chauhan', 'Rajput', 'Thakur'
]

def random_date(days_back=365):
    return (datetime.utcnow() - timedelta(days=random.randint(0, days_back))).isoformat()

def random_phone():
    return f"+91-{random.randint(7000000000, 9999999999)}"

def random_email(name):
    domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'proton.me']
    n = name.lower().replace(' ', '.')
    return f"{n}{random.randint(1, 999)}@{random.choice(domains)}"

def random_handle(name):
    n = name.lower().replace(' ', '_')
    return f"@{n}{random.randint(1, 999)}"

def random_ip():
    return f"{random.randint(1,254)}.{random.randint(0,254)}.{random.randint(0,254)}.{random.randint(1,254)}"

def random_lat_lon():
    lat = round(random.uniform(8.4, 37.6), 6)
    lon = round(random.uniform(68.7, 97.4), 6)
    return lat, lon

def generate_behavioral_profile():
    patterns = random.sample(BEHAVIORAL_PATTERNS, random.randint(2, 5))
    spending = {cat: round(random.uniform(0, 1), 3) for cat in random.sample(SPENDING_CATEGORIES, random.randint(3, 8))}
    return {
        "behavioral_patterns": patterns,
        "spending_categories": spending,
        "digital_activity_score": round(random.uniform(0, 100), 2),
        "financial_health_score": round(random.uniform(0, 100), 2),
        "social_influence_score": round(random.uniform(0, 100), 2),
        "mobility_index": round(random.uniform(0, 10), 2),
        "purchase_frequency": random.choice(['daily', 'weekly', 'monthly', 'quarterly']),
        "avg_transaction_value": round(random.uniform(100, 50000), 2),
        "credit_risk_signal": round(random.uniform(0, 1), 4),
        "churn_probability": round(random.uniform(0, 1), 4),
        "upi_transaction_count_monthly": random.randint(0, 200),
        "ecommerce_orders_monthly": random.randint(0, 30),
        "streaming_hours_daily": round(random.uniform(0, 8), 1),
        "news_consumption_score": round(random.uniform(0, 1), 3),
        "political_sensitivity": random.choice(['LOW', 'MEDIUM', 'HIGH']),
        "brand_affinity": {
            "primary": random.choice(['Amazon', 'Flipkart', 'Jio', 'Airtel', 'Zomato', 'Swiggy']),
            "secondary": random.choice(['Netflix', 'Hotstar', 'Spotify', 'PhonePe', 'Paytm'])
        },
        "peak_activity_hours": random.sample(list(range(24)), 4),
        "device_primary": random.choice(DEVICE_TYPES),
        "telco_provider": random.choice(TELCOS),
        "data_consumption_gb_monthly": round(random.uniform(1, 50), 1),
    }

def generate_situational_intelligence():
    lat, lon = random_lat_lon()
    city = random.choice(INDIAN_CITIES)
    state = random.choice(STATES)
    recent_events = []
    for _ in range(random.randint(1, 5)):
        event = random.choice(EVENT_TYPES)
        recent_events.append({
            "event_type": event,
            "impact_score": round(random.uniform(0, 1), 3),
            "behavioral_change_detected": random.choice([True, False]),
            "timestamp": random_date(30)
        })
    return {
        "current_location": {
            "city": city, "state": state, "lat": lat, "lon": lon,
            "location_type": random.choice(['home', 'work', 'transit', 'retail', 'unknown'])
        },
        "home_location": {"city": city, "state": state, "pin_code": str(random.randint(100000, 999999))},
        "work_location": {"city": random.choice(INDIAN_CITIES), "state": random.choice(STATES)},
        "mobility_pattern": random.choice(['static', 'local', 'regional', 'national']),
        "venue_visits_monthly": random.randint(0, 50),
        "venue_categories": random.sample(['mall', 'restaurant', 'gym', 'hospital', 'office', 'airport', 'metro', 'school'], random.randint(1, 4)),
        "recent_event_impacts": recent_events,
        "situational_risk_level": random.choice(RISK_LEVELS),
        "geopolitical_exposure": round(random.uniform(0, 1), 3),
        "economic_vulnerability_index": round(random.uniform(0, 1), 3),
        "social_network_density": random.randint(10, 2000),
        "influence_reach": random.randint(0, 100000),
        "last_physical_signal": random_date(7),
        "last_digital_signal": random_date(1),
    }

def generate_oracle_predictions():
    predictions = {}
    horizons = ['24h', '7d', '30d', '90d', '365d']
    for domain in PREDICTION_DOMAINS:
        predictions[domain] = {}
        for horizon in horizons:
            predictions[domain][horizon] = {
                "action": f"{domain}_action_{random.randint(1,10)}",
                "probability": round(random.uniform(0, 1), 4),
                "confidence": round(random.uniform(0.5, 0.99), 3),
                "trigger_conditions": random.sample(['price_drop', 'season_change', 'life_event', 'peer_influence', 'marketing_exposure'], random.randint(1, 3)),
                "estimated_value": round(random.uniform(100, 100000), 2)
            }
    return {
        "oracle_version": "2.1.0",
        "last_refresh": random_date(1),
        "next_refresh": (datetime.utcnow() + timedelta(hours=4)).isoformat(),
        "predictions": predictions,
        "overall_activity_score": round(random.uniform(0, 100), 2),
        "life_stage": random.choice(['student', 'early_career', 'mid_career', 'senior', 'retired']),
        "life_events_detected": random.sample(['job_change', 'marriage', 'new_baby', 'home_purchase', 'relocation'], random.randint(0, 3))
    }

def generate_stratum_id(name, phone):
    return f"STRID-{uuid.uuid4().hex[:8].upper()}-{uuid.uuid4().hex[:4].upper()}"

def generate_identity_anchors(name, phone, email, handle):
    return {
        "phone_anchor": phone,
        "email_anchor": email,
        "device_fingerprint": f"DEV-{uuid.uuid4().hex[:12].upper()}",
        "payment_id": f"UPI-{uuid.uuid4().hex[:10].upper()}",
        "social_handle": handle,
        "biometric_hash": f"BIO-{uuid.uuid4().hex[:16].upper()}",
        "resolution_confidence": round(random.uniform(0.7, 0.99), 4),
        "kyc_verified": random.choice([True, False]),
        "anchor_count": random.randint(3, 6),
        "last_verified": random_date(90)
    }

# ── Main Generator ─────────────────────────────────────────────
print(f"Connecting to database: {DB_PATH}")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# ── FIX 1: Load existing IDs to guarantee no collision ────────
cursor.execute("SELECT COUNT(*) FROM identities")
existing = cursor.fetchone()[0]
print(f"Existing profiles: {existing}")

cursor.execute("SELECT id FROM identities WHERE id IS NOT NULL")
seen_ids = set(row[0] for row in cursor.fetchall())
print(f"Loaded {len(seen_ids):,} existing IDs into memory")

cursor.execute("SELECT handle FROM identities WHERE handle IS NOT NULL")
seen_handles = set(row[0] for row in cursor.fetchall())

print(f"Generating {TARGET_PROFILES} new profiles...")
print("This may take a few minutes...")

count = 0
batch_size = 1000
batch = []

for i in range(TARGET_PROFILES):
    try:
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}"
        phone = random_phone()
        email = random_email(f"{first}{last}")
        handle = random_handle(f"{first}{last}")

        # Ensure unique handle
        while handle in seen_handles:
            handle = random_handle(f"{first}{last}{random.randint(1,9999)}")
        seen_handles.add(handle)

        # ── FIX 2: Use FULL uuid4 (32 hex chars) — zero collision risk ──
        identity_id = f"id-{uuid.uuid4().hex}"   # e.g. id-3f2504e04f8911d39a0c0305e82c3301
        while identity_id in seen_ids:            # paranoid check, practically never triggers
            identity_id = f"id-{uuid.uuid4().hex}"
        seen_ids.add(identity_id)

        stratum_id = generate_stratum_id(name, phone)
        behavioral = generate_behavioral_profile()
        situational = generate_situational_intelligence()
        oracle = generate_oracle_predictions()
        anchors = generate_identity_anchors(name, phone, email, handle)

        extra = json.dumps({
            "stratum_id": stratum_id,
            "identity_anchors": anchors,
            "behavioral_intelligence": behavioral,
            "situational_intelligence": situational,
            "oracle_predictions": oracle,
            "demographic": {
                "age": random.randint(18, 65),
                "gender": random.choice(['M', 'F', 'NB']),
                "occupation": random.choice(OCCUPATIONS),
                "income_band": random.choice(INCOME_BANDS),
                "education": random.choice(['High School', 'Bachelor', 'Master', 'PhD', 'Diploma']),
                "marital_status": random.choice(['Single', 'Married', 'Divorced', 'Widowed'])
            },
            "risk_profile": {
                "overall_risk": random.choice(RISK_LEVELS),
                "financial_risk": round(random.uniform(0, 1), 3),
                "security_risk": round(random.uniform(0, 1), 3),
                "behavioral_risk": round(random.uniform(0, 1), 3)
            },
            "consent": {
                "data_processing": random.choice([True, False]),
                "marketing": random.choice([True, False]),
                "analytics": random.choice([True, False]),
                "consent_date": random_date(180),
                "consent_version": "2.1"
            },
            "platform_signals": {
                "ip_address": random_ip(),
                "platform": random.choice(PLATFORMS),
                "first_seen": random_date(365),
                "last_active": random_date(7),
                "activity_score": round(random.uniform(0, 100), 2)
            }
        })

        batch.append((
            identity_id,
            name,
            random.choice(PLATFORMS),
            email,
            phone,
            handle,
            extra,
            NOW
        ))
        count += 1

        if len(batch) >= batch_size:
            # ── FIX 3: INSERT OR IGNORE as safety net for any edge case ──
            cursor.executemany(
                "INSERT OR IGNORE INTO identities (id, name, platform, email, phone, handle, extra, created_at) VALUES (?,?,?,?,?,?,?,?)",
                batch
            )
            conn.commit()
            batch = []
            print(f"  Progress: {count:,} / {TARGET_PROFILES:,} profiles created...")

    except Exception as e:
        print(f"  Warning at record {count}: {e}")
        continue

# Insert remaining
if batch:
    cursor.executemany(
        "INSERT OR IGNORE INTO identities (id, name, platform, email, phone, handle, extra, created_at) VALUES (?,?,?,?,?,?,?,?)",
        batch
    )
    conn.commit()

# Final count
cursor.execute("SELECT COUNT(*) FROM identities")
total = cursor.fetchone()[0]
print(f"\n{'='*60}")
print(f"STRATUM OMNIS PROFILE GENERATION COMPLETE")
print(f"New profiles created:  {count:,}")
print(f"Total in database:     {total:,}")
print(f"{'='*60}")

# Export sample to JSON
print("\nExporting profiles to JSON...")
cursor.execute("SELECT id, name, platform, email, phone, handle, extra, created_at FROM identities LIMIT 100000")
rows = cursor.fetchall()
cols = ['id', 'name', 'platform', 'email', 'phone', 'handle', 'extra', 'created_at']
profiles = []
for row in rows:
    p = dict(zip(cols, row))
    if p.get('extra'):
        try:
            p['extra'] = json.loads(p['extra'])
        except:
            pass
    profiles.append(p)

with open('stratum_profiles_100k.json', 'w') as f:
    json.dump(profiles, f, indent=2, default=str)

print(f"Exported {len(profiles):,} profiles to stratum_profiles_100k.json")
conn.close()
print("\nDONE!")