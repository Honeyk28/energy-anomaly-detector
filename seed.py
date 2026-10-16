import os
import pandas as pd
from werkzeug.security import generate_password_hash
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from db import init_db, get_db

# Read passwords from environment variables; secure defaults provided if not set in environment
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Team@2026#1")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "Demo@2026")

SEED_USERS = [
    {"username": "member1", "display_name": "Member 1", "role": "admin", "password": os.getenv("MEMBER1_PASSWORD", ADMIN_PASSWORD)},
    {"username": "member2", "display_name": "Member 2", "role": "admin", "password": os.getenv("MEMBER2_PASSWORD", ADMIN_PASSWORD)},
    {"username": "member3", "display_name": "Member 3", "role": "admin", "password": os.getenv("MEMBER3_PASSWORD", ADMIN_PASSWORD)},
    {"username": "demo",    "display_name": "Demo User", "role": "viewer", "password": DEMO_PASSWORD},
]

def seed():
    print("Initializing database...")
    init_db()

    with get_db() as conn:
        cursor = conn.cursor()
        print("Seeding user accounts...")
        now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        for u in SEED_USERS:
            pwd_hash = generate_password_hash(u["password"], method='pbkdf2:sha256')
            cursor.execute("""
                INSERT INTO users (username, display_name, role, password_hash, is_active, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(username) DO UPDATE SET
                    display_name = excluded.display_name,
                    role = excluded.role,
                    password_hash = excluded.password_hash
            """, (u["username"], u["display_name"], u["role"], pwd_hash, now))
        
        csv_path = os.path.join(os.path.dirname(__file__), 'data', 'SM_Cleaned_Data_MH_Aggregated.csv')
        if os.path.exists(csv_path):
            print(f"Loading smart meter readings from {csv_path}...")
            df = pd.read_csv(csv_path)
            
            # Verify and extract expected columns: meter, Date, t_kWh
            required_cols = {'meter', 'Date', 't_kWh'}
            if not required_cols.issubset(set(df.columns)):
                raise ValueError(f"Dataset missing required columns. Expected {required_cols}, found {df.columns.tolist()}")
            
            records = []
            for _, row in df.iterrows():
                m_str = str(row['meter']).strip()
                d_str = str(row['Date']).strip()
                kwh_val = float(row['t_kWh'])
                records.append((m_str, d_str, kwh_val))
            
            cursor.executemany("""
                INSERT OR REPLACE INTO readings (meter, date, kwh)
                VALUES (?, ?, ?)
            """, records)
            
            unique_meters = sorted(list(set(r[0] for r in records)))
            min_date = min(r[1] for r in records)
            max_date = max(r[1] for r in records)
            zero_count = sum(1 for r in records if r[2] == 0)
            
            print(f"Loaded {len(records)} readings across {len(unique_meters)} meters ({min_date} to {max_date}).")
            print(f"Zero readings: {zero_count} (outages / non-reporting).")
        else:
            print(f"WARNING: CSV dataset not found at {csv_path}")

        conn.commit()
    print("Seeding complete.")

if __name__ == '__main__':
    seed()
