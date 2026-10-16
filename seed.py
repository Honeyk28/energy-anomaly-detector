import os
import pandas as pd
from werkzeug.security import generate_password_hash
from datetime import datetime
from db import init_db, get_db

SEED_USERS = [
    {"username": "member1", "display_name": "Member 1", "role": "admin", "password": "Team@2026#1"},
    {"username": "member2", "display_name": "Member 2", "role": "admin", "password": "Team@2026#2"},
    {"username": "member3", "display_name": "Member 3", "role": "admin", "password": "Team@2026#3"},
    {"username": "demo",    "display_name": "Demo User", "role": "viewer", "password": "Demo@2026"},
]

def seed():
    print("Initializing database...")
    init_db()

    with get_db() as conn:
        cursor = conn.cursor()
        print("Seeding users...")
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
            print(f"Loading readings from {csv_path}...")
            df = pd.read_csv(csv_path)
            # Ensure correct columns and types
            records = []
            for _, row in df.iterrows():
                records.append((str(row['meter']).strip(), str(row['Date']).strip(), float(row['t_kWh'])))
            
            cursor.executemany("""
                INSERT OR REPLACE INTO readings (meter, date, kwh)
                VALUES (?, ?, ?)
            """, records)
            print(f"Loaded {len(records)} readings.")
        else:
            print(f"WARNING: CSV not found at {csv_path}")

        conn.commit()
    print("Seeding complete.")

if __name__ == '__main__':
    seed()
