"""
STRATUM OMNIS Entity Profile Generator — VERSION 2 (COMPLETE)
Adds all missing fields:
  1. Financial DNA Score
  2. Life Event Radar
  3. Psychographic Inference (Big Five + Schwartz values)
  4. Social Graph Features
  5. Geopolitical Sensitivity Index
"""
import sqlite3
import uuid
import json
import random
import math
from datetime import datetime, timedelta

# ── Constants ──────────────────────────────────────────────────
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
PREDICTION_DOMAINS = ['purchase', 'financial', 'mobility', 'digital', 'social']
EVENT_TYPES = [
    'repo_rate_change', 'election_announcement', 'natural_disaster',
    'market_crash', 'new_product_launch', 'policy_change',
    'inflation_spike', 'employment_data', 'geopolitical_tension',
    'pandemic_alert', 'festival_season', 'budget_announcement'
]
LIFE_EVENTS = [
    'job_change', 'marriage', 'new_baby', 'home_purchase',
    'relocation', 'divorce', 'bereavement', 'graduation',
    'vehicle_purchase', 'health_crisis', 'retirement', 'business_launch'
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

# ── FIELD 1: Financial DNA Score ────────────────────────────────
def generate_financial_dna():
    """
    STRATUM Financial DNA — Alternative credit intelligence.
    Mirrors STRATUM FINANCIAL DNA™ product spec.
    """
    credit_score = random.randint(300, 900)
    return {
        "credit_score": credit_score,
        "credit_band": (
            "EXCELLENT" if credit_score > 750 else
            "GOOD" if credit_score > 650 else
            "FAIR" if credit_score > 550 else
            "POOR"
        ),
        "default_probability_6m": round(random.uniform(0, 1), 4),
        "score_confidence_interval": [
            max(300, credit_score - random.randint(20, 50)),
            min(900, credit_score + random.randint(20, 50))
        ],
        "financial_stress_composite": round(random.uniform(0, 1), 3),
        "spend_velocity_monthly": round(random.uniform(1000, 200000), 2),
        "discretionary_spend_ratio": round(random.uniform(0.1, 0.9), 3),
        "essential_spend_ratio": round(random.uniform(0.1, 0.9), 3),
        "merchant_loyalty_score": round(random.uniform(0, 1), 3),
        "price_sensitivity_index": round(random.uniform(0, 1), 3),
        "payment_timing_regularity": round(random.uniform(0, 1), 3),
        "savings_behavior_signal": random.choice(['HIGH', 'MEDIUM', 'LOW', 'NONE']),
        "bnpl_usage_pattern": random.choice(['frequent', 'occasional', 'never']),
        "revolving_balance_behavior": random.choice(['carries_balance', 'pays_in_full', 'no_card']),
        "income_stability_index": round(random.uniform(0, 1), 3),
        "financial_distress_signal_45d": random.choice([True, False]),
        "upi_transaction_regularity": round(random.uniform(0, 1), 3),
        "category_diversification_index": round(random.uniform(0, 1), 3),
        "model_version": "FinDNA_v2.1",
        "last_scored": random_date(7)
    }

# ── FIELD 2: Life Event Radar ───────────────────────────────────
def generate_life_event_radar():
    """
    STRATUM Life Event Radar — Predicts major life events 45–90 days ahead.
    Mirrors STRATUM LIFE EVENT RADAR™ product spec.
    """
    n_events = random.randint(0, 4)
    detected_events = []
    for _ in range(n_events):
        event = random.choice(LIFE_EVENTS)
        detected_events.append({
            "event_type": event,
            "probability": round(random.uniform(0.5, 0.99), 3),
            "predicted_window_days": random.randint(7, 90),
            "confidence": round(random.uniform(0.6, 0.99), 3),
            "signal_convergence_count": random.randint(2, 6),
            "detected_at": random_date(14)
        })

    # Probability vector across all 12 life event categories
    life_event_probs = {e: round(random.uniform(0, 1), 3) for e in LIFE_EVENTS}

    return {
        "active_detected_events": detected_events,
        "life_event_probability_vector": life_event_probs,
        "life_stage": random.choice([
            'student', 'early_career', 'mid_career',
            'senior_career', 'pre_retirement', 'retired'
        ]),
        "life_stage_stability_index": round(random.uniform(0, 1), 3),
        "transition_velocity": round(random.uniform(0, 1), 3),
        "next_predicted_event": random.choice(LIFE_EVENTS),
        "next_event_horizon_days": random.randint(7, 180),
        "historical_events_detected": random.sample(LIFE_EVENTS, random.randint(0, 5)),
        "model_accuracy_on_cohort": round(random.uniform(0.80, 0.95), 3),
        "last_refresh": random_date(1)
    }

# ── FIELD 3: Psychographic Inference ───────────────────────────
def generate_psychographic_profile():
    """
    STRATUM Psychographic Inference — Big Five personality + Schwartz values.
    Mirrors STRATUM ML Model Hub spec (Psychographic Inference Model).
    """
    # Big Five personality dimensions (0–1 scale)
    big_five = {
        "openness": round(random.uniform(0, 1), 3),
        "conscientiousness": round(random.uniform(0, 1), 3),
        "extraversion": round(random.uniform(0, 1), 3),
        "agreeableness": round(random.uniform(0, 1), 3),
        "neuroticism": round(random.uniform(0, 1), 3)
    }

    # Schwartz Basic Human Values (10 dimensions)
    schwartz_values = {
        "self_direction": round(random.uniform(0, 1), 3),
        "stimulation": round(random.uniform(0, 1), 3),
        "hedonism": round(random.uniform(0, 1), 3),
        "achievement": round(random.uniform(0, 1), 3),
        "power": round(random.uniform(0, 1), 3),
        "security": round(random.uniform(0, 1), 3),
        "conformity": round(random.uniform(0, 1), 3),
        "tradition": round(random.uniform(0, 1), 3),
        "benevolence": round(random.uniform(0, 1), 3),
        "universalism": round(random.uniform(0, 1), 3)
    }

    return {
        "big_five": big_five,
        "schwartz_values": schwartz_values,
        "risk_tolerance_index": round(random.uniform(0, 1), 3),
        "risk_tolerance_category": random.choice(['very_low', 'low', 'medium', 'high', 'very_high']),
        "brand_affinity_cluster": random.choice([
            'premium_seeker', 'value_hunter', 'brand_loyal',
            'experience_first', 'sustainable_conscious', 'convenience_driven'
        ]),
        "innovation_adoption_category": random.choice([
            'innovator', 'early_adopter', 'early_majority',
            'late_majority', 'laggard'
        ]),
        "quality_vs_value_orientation": round(random.uniform(0, 1), 3),
        "social_conformity_index": round(random.uniform(0, 1), 3),
        "impulse_control_score": round(random.uniform(0, 1), 3),
        "environmental_consciousness": round(random.uniform(0, 1), 3),
        "political_orientation_signal": random.choice([
            'progressive', 'moderate', 'conservative', 'apolitical', 'undetermined'
        ]),
        "validation_correlation_r": round(random.uniform(0.65, 0.85), 3),
        "model_version": "PsychInfer_v1.4",
        "last_inferred": random_date(30)
    }

# ── FIELD 4: Social Graph Features ─────────────────────────────
def generate_social_graph_features():
    """
    STRATUM Social Graph Intelligence — Influence network analysis.
    Mirrors STRATUM SOCIAL GRAPH INTELLIGENCE™ product spec.
    """
    n_communities = random.randint(1, 6)
    communities = []
    for i in range(n_communities):
        communities.append({
            "community_id": f"COM-{uuid.uuid4().hex[:8].upper()}",
            "community_type": random.choice([
                'family', 'professional', 'social', 'interest_group',
                'neighborhood', 'religious', 'political'
            ]),
            "membership_probability": round(random.uniform(0.5, 1.0), 3),
            "role_in_community": random.choice([
                'influencer', 'connector', 'follower', 'peripheral', 'core_member'
            ])
        })

    return {
        "degree_centrality": round(random.uniform(0, 1), 4),
        "betweenness_centrality": round(random.uniform(0, 1), 4),
        "closeness_centrality": round(random.uniform(0, 1), 4),
        "eigenvector_centrality": round(random.uniform(0, 1), 4),
        "influence_authority_score": round(random.uniform(0, 100), 2),
        "influence_category": random.choice([
            'mega_influencer', 'macro_influencer', 'micro_influencer',
            'nano_influencer', 'non_influencer'
        ]),
        "social_network_size": random.randint(10, 5000),
        "strong_ties_count": random.randint(2, 50),
        "weak_ties_count": random.randint(10, 500),
        "community_memberships": communities,
        "social_decay_index": round(random.uniform(0, 1), 3),
        "communication_recency_score": round(random.uniform(0, 1), 3),
        "household_size_estimate": random.randint(1, 8),
        "household_membership_probability": round(random.uniform(0.7, 1.0), 3),
        "professional_network_density": round(random.uniform(0, 1), 3),
        "social_mobility_score": round(random.uniform(0, 1), 3),
        "information_cascade_position": random.choice([
            'originator', 'early_amplifier', 'mid_chain', 'late_adopter', 'terminal'
        ]),
        "graphsage_embedding_dim": 256,
        "community_detection_algorithm": "Louvain",
        "last_graph_update": random_date(1)
    }

# ── FIELD 5: Geopolitical Sensitivity Index ─────────────────────
def generate_geopolitical_sensitivity():
    """
    STRATUM Geopolitical Sensitivity — Event-to-behavior cascade modeling.
    Mirrors STRATUM SITUATIONAL INTELLIGENCE FEED™ product spec.
    """
    event_categories = [
        'monetary_policy', 'fiscal_policy', 'election',
        'natural_disaster', 'supply_chain_shock', 'commodity_price',
        'labor_market', 'geopolitical_conflict', 'regulatory_change',
        'health_emergency', 'infrastructure_event', 'climate_event'
    ]

    sensitivity_scores = {
        cat: round(random.uniform(0, 1), 3) for cat in event_categories
    }

    recent_impacts = []
    for _ in range(random.randint(0, 4)):
        recent_impacts.append({
            "event_type": random.choice(event_categories),
            "event_magnitude": random.choice(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']),
            "behavioral_impact_score": round(random.uniform(0, 1), 3),
            "impact_direction": random.choice(['positive', 'negative', 'neutral']),
            "behavioral_lag_days": random.randint(0, 30),
            "affected_domains": random.sample(
                ['spending', 'mobility', 'communication', 'savings', 'investment'],
                random.randint(1, 3)
            ),
            "detected_at": random_date(90)
        })

    return {
        "overall_geopolitical_exposure": round(random.uniform(0, 1), 3),
        "economic_vulnerability_index": round(random.uniform(0, 1), 3),
        "policy_sensitivity_index": round(random.uniform(0, 1), 3),
        "event_category_sensitivity": sensitivity_scores,
        "economic_shock_resilience": round(random.uniform(0, 1), 3),
        "behavioral_lag_distribution": {
            "mean_days": round(random.uniform(1, 21), 1),
            "std_days": round(random.uniform(1, 10), 1),
            "min_days": random.randint(0, 5),
            "max_days": random.randint(15, 60)
        },
        "recent_event_impacts": recent_impacts,
        "macro_event_alert_subscriptions": random.sample(event_categories, random.randint(0, 4)),
        "situational_risk_level": random.choice(RISK_LEVELS),
        "cascade_model_version": "SICM_v2.0",
        "last_cascade_refresh": random_date(4)
    }

# ── Existing generators (unchanged) ─────────────────────────────
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
        recent_events.append({
            "event_type": random.choice(EVENT_TYPES),
            "impact_score": round(random.uniform(0, 1), 3),
            "behavioral_change_detected": random.choice([True, False]),
            "timestamp": random_date(30)
        })
    return {
        "current_location": {"city": city, "state": state, "lat": lat, "lon": lon,
            "location_type": random.choice(['home', 'work', 'transit', 'retail', 'unknown'])},
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
    horizons = ['6h', '24h', '7d', '30d', '90d']
    domains = ['commercial', 'non_commercial', 'personal_trajectory', 'environmental_response', 'geopolitical_response']
    for domain in domains:
        predictions[domain] = {}
        for horizon in horizons:
            predictions[domain][horizon] = {
                "action": f"{domain}_action_{random.randint(1,10)}",
                "probability": round(random.uniform(0, 1), 4),
                "confidence": round(random.uniform(0.5, 0.99), 3),
                "confidence_interval": [
                    round(random.uniform(0.3, 0.6), 3),
                    round(random.uniform(0.7, 0.99), 3)
                ],
                "trigger_conditions": random.sample(
                    ['price_drop', 'season_change', 'life_event', 'peer_influence', 'marketing_exposure'],
                    random.randint(1, 3)
                ),
                "causal_chain": random.sample(
                    ['income_signal', 'location_pattern', 'social_influence', 'event_cascade', 'behavioral_shift'],
                    random.randint(1, 3)
                ),
                "estimated_value": round(random.uniform(100, 100000), 2)
            }
    return {
        "oracle_version": "ORACLE_v2.1",
        "last_refresh": random_date(1),
        "next_refresh": (datetime.utcnow() + timedelta(hours=4)).isoformat(),
        "predictions": predictions,
        "overall_activity_score": round(random.uniform(0, 100), 2),
        "recommended_actions_for_clients": {
            "advertiser": f"Activate campaign — {random.randint(60,95)}% intent probability detected.",
            "lender": f"Pre-approve offer — financial capacity signal confirmed.",
            "insurer": f"Life event cross-sell window: {random.randint(7,30)} days."
        }
    }

def generate_identity_anchors(name, phone, email, handle):
    return {
        "phone_anchor": phone,
        "email_anchor": email,
        "aadhaar_token": f"AADH-{uuid.uuid4().hex[:16].upper()}",
        "device_fingerprint": f"DEV-{uuid.uuid4().hex[:12].upper()}",
        "payment_id_upi": f"UPI-{uuid.uuid4().hex[:10].upper()}",
        "social_handle": handle,
        "biometric_voice_hash": f"BIO-{uuid.uuid4().hex[:16].upper()}",
        "resolution_confidence": round(random.uniform(0.7, 0.99), 4),
        "kyc_verified": random.choice([True, False]),
        "verification_tier": random.choice(['aadhaar_anchored', 'probabilistic', 'device_only']),
        "anchor_count": random.randint(3, 6),
        "last_verified": random_date(90)
    }

# ── Main Generator ──────────────────────────────────────────────
print(f"Connecting to database: {DB_PATH}")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM identities")
existing = cursor.fetchone()[0]
print(f"Existing profiles: {existing:,}")

# Load existing IDs and handles to avoid collisions
cursor.execute("SELECT id FROM identities WHERE id IS NOT NULL")
seen_ids = set(row[0] for row in cursor.fetchall())
cursor.execute("SELECT handle FROM identities WHERE handle IS NOT NULL")
seen_handles = set(row[0] for row in cursor.fetchall())
print(f"Loaded {len(seen_ids):,} existing IDs into memory")

print(f"Generating {TARGET_PROFILES:,} new COMPLETE profiles...")
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

        while handle in seen_handles:
            handle = random_handle(f"{first}{last}{random.randint(1,9999)}")
        seen_handles.add(handle)

        # Full UUID — zero collision risk
        identity_id = f"id-{uuid.uuid4().hex}"
        while identity_id in seen_ids:
            identity_id = f"id-{uuid.uuid4().hex}"
        seen_ids.add(identity_id)

        stratum_id = f"STRID-{uuid.uuid4().hex[:8].upper()}-{uuid.uuid4().hex[:4].upper()}"

        # Build COMPLETE extra JSON with ALL 5 new fields
        extra = json.dumps({
            "stratum_id": stratum_id,
            "identity_anchors": generate_identity_anchors(name, phone, email, handle),
            "behavioral_intelligence": generate_behavioral_profile(),
            "situational_intelligence": generate_situational_intelligence(),
            "oracle_predictions": generate_oracle_predictions(),

            # ── 5 NEW COMPLETE FIELDS ──────────────────────────
            "financial_dna": generate_financial_dna(),
            "life_event_radar": generate_life_event_radar(),
            "psychographic_profile": generate_psychographic_profile(),
            "social_graph": generate_social_graph_features(),
            "geopolitical_sensitivity": generate_geopolitical_sensitivity(),
            # ──────────────────────────────────────────────────

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
                "consent_version": "2.1",
                "dpdp_compliant": True
            },
            "platform_signals": {
                "ip_address": random_ip(),
                "platform": random.choice(PLATFORMS),
                "first_seen": random_date(365),
                "last_active": random_date(7),
                "activity_score": round(random.uniform(0, 100), 2)
            },
            "schema_version": "STRATUM_OMNIS_v2.0"
        })

        batch.append((
            identity_id, name, random.choice(PLATFORMS),
            email, phone, handle, extra, NOW
        ))
        count += 1

        if len(batch) >= batch_size:
            cursor.executemany(
                "INSERT OR IGNORE INTO identities (id, name, platform, email, phone, handle, extra, created_at) VALUES (?,?,?,?,?,?,?,?)",
                batch
            )
            conn.commit()
            batch = []
            print(f"  Progress: {count:,} / {TARGET_PROFILES:,} profiles created...")

    except Exception as e:
        print(f"  Warning at {count}: {e}")
        continue

# Insert remaining
if batch:
    cursor.executemany(
        "INSERT OR IGNORE INTO identities (id, name, platform, email, phone, handle, extra, created_at) VALUES (?,?,?,?,?,?,?,?)",
        batch
    )
    conn.commit()

cursor.execute("SELECT COUNT(*) FROM identities")
total = cursor.fetchone()[0]

print(f"\n{'='*60}")
print(f"STRATUM OMNIS v2 — COMPLETE PROFILE GENERATION DONE")
print(f"New profiles created : {count:,}")
print(f"Total in database    : {total:,}")
print(f"Fields per profile   : ALL 14 (including 5 new fields)")
print(f"{'='*60}")
print("\nNew fields added to every profile:")
print("  ✅ Financial DNA Score (credit, stress, spend velocity)")
print("  ✅ Life Event Radar (12 event categories, 45-90d horizon)")
print("  ✅ Psychographic Profile (Big Five + Schwartz values)")
print("  ✅ Social Graph Features (centrality, communities, influence)")
print("  ✅ Geopolitical Sensitivity (12 event categories, cascade)")

conn.close()
print("\nDONE!")