import os
import sys
import unittest
import json

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from db import init_db, get_db, get_user_by_username, update_user_status
from seed import seed, SEED_USERS

class SmokeTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        init_db()
        seed()

    def setUp(self):
        self.client = app.test_client()

    def test_01_unauthenticated_api_returns_401(self):
        """Unauthenticated /api/overview returns 401"""
        res = self.client.get('/api/overview')
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertIn('error', data)

    def test_02_each_seed_user_can_login(self):
        """Each seed user can log in"""
        for u in SEED_USERS:
            c = app.test_client()
            res = c.post('/login', data={
                'username': u['username'],
                'password': u['password']
            }, follow_redirects=False)
            self.assertEqual(res.status_code, 302, f"User {u['username']} failed to redirect on login")
            
            # Verify session is authenticated by fetching /api/overview
            res_api = c.get('/api/overview')
            self.assertEqual(res_api.status_code, 200, f"User {u['username']} failed to access authenticated API")

    def test_03_disabled_user_blocked_immediately(self):
        """A disabled user is blocked immediately, even with active session"""
        c = app.test_client()
        # Login demo
        res = c.post('/login', data={'username': 'demo', 'password': 'Demo@2026'}, follow_redirects=False)
        self.assertEqual(res.status_code, 302)

        demo_user = get_user_by_username('demo')
        admin_user = get_user_by_username('member1')
        self.assertIsNotNone(demo_user)

        # Disable demo user
        update_user_status(demo_user.id, False, admin_user.id)

        try:
            # Active session now rejected
            res_blocked = c.get('/api/overview')
            self.assertEqual(res_blocked.status_code, 401)
            err_data = res_blocked.get_json()
            self.assertIn("Access has been disabled", err_data.get('error', ''))

            # Subsequent login attempt is blocked
            c2 = app.test_client()
            res_login = c2.post('/login', data={'username': 'demo', 'password': 'Demo@2026'}, follow_redirects=True)
            self.assertIn(b"Access has been disabled", res_login.data)
        finally:
            # Re-enable demo for other tests
            update_user_status(demo_user.id, True, admin_user.id)

    def test_04_viewer_gets_403_on_admin_routes(self):
        """Viewer gets 403 on /api/users"""
        c = app.test_client()
        c.post('/login', data={'username': 'demo', 'password': 'Demo@2026'})
        
        res = c.get('/api/users')
        self.assertEqual(res.status_code, 403)
        
        res_post = c.post('/api/users', json={'username': 'test', 'password': 'password'})
        self.assertEqual(res_post.status_code, 403)

    def test_05_detect_returns_at_least_one_anomaly(self):
        """/api/detect returns >= 1 anomaly with default settings"""
        c = app.test_client()
        c.post('/login', data={'username': 'member1', 'password': 'Team@2026#1'})
        
        res = c.get('/api/detect')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('anomalies', data)
        self.assertGreaterEqual(len(data['anomalies']), 1, "Expected at least 1 anomaly flagged with default settings")
        print(f"\n[SmokeTest] Detected {len(data['anomalies'])} anomalies with default settings.")

    def test_06_house_excess_sum_equals_increase(self):
        """For the top anomaly, sum of house excess equals increase within 0.01"""
        c = app.test_client()
        c.post('/login', data={'username': 'member1', 'password': 'Team@2026#1'})

        # Get overview and top anomaly
        res_ov = c.get('/api/overview')
        self.assertEqual(res_ov.status_code, 200)
        ov = res_ov.get_json()
        top_anomaly = ov['top_anomaly']
        self.assertIsNotNone(top_anomaly)
        
        target_date = top_anomaly['date']
        target_increase = top_anomaly['increase']

        # Get households for target date
        res_hh = c.get(f'/api/households?date={target_date}&top=all')
        self.assertEqual(res_hh.status_code, 200)
        houses = res_hh.get_json()
        self.assertGreater(len(houses), 0)

        # Sum of excesses
        sum_excess = sum(h['excess'] for h in houses)
        diff = abs(sum_excess - target_increase)
        print(f"\n[SmokeTest] Date: {target_date}, House count: {len(houses)}, Sum excess: {sum_excess:.4f}, Increase: {target_increase:.4f}, Diff: {diff:.6f}")
        self.assertLessEqual(diff, 0.01, f"Sum of house excess {sum_excess} differs from increase {target_increase} by {diff}")

if __name__ == '__main__':
    unittest.main()
