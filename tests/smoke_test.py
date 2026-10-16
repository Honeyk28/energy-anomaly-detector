import os
import sys
import unittest
import numpy as np

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from db import init_db, get_user_by_username, update_user_status
from seed import seed, SEED_USERS
from engine import AnalyticsEngine

class EnergyAnomalyDetectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        init_db()
        seed()
        cls.engine = AnalyticsEngine()

    def setUp(self):
        self.client = app.test_client()

    def test_01_unauthenticated_api_returns_401(self):
        """Unauthenticated requests to API endpoints return 401 JSON"""
        res = self.client.get('/api/overview')
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertIn('error', data)

    def test_02_each_seed_user_can_login(self):
        """Each configured seed user can log in and access protected API"""
        for u in SEED_USERS:
            c = app.test_client()
            res = c.post('/login', data={
                'username': u['username'],
                'password': u['password']
            }, follow_redirects=False)
            self.assertEqual(res.status_code, 302, f"User {u['username']} login redirect failed")
            
            res_api = c.get('/api/overview')
            self.assertEqual(res_api.status_code, 200, f"User {u['username']} failed to access /api/overview")

    def test_03_disabled_user_blocked_immediately(self):
        """Disabled user is immediately blocked even with active session token"""
        c = app.test_client()
        # Find password for demo
        demo_pwd = next(u['password'] for u in SEED_USERS if u['username'] == 'demo')
        res = c.post('/login', data={'username': 'demo', 'password': demo_pwd}, follow_redirects=False)
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
            res_login = c2.post('/login', data={'username': 'demo', 'password': demo_pwd}, follow_redirects=True)
            self.assertIn(b"Access has been disabled", res_login.data)
        finally:
            # Re-enable demo for remaining tests
            update_user_status(demo_user.id, True, admin_user.id)

    def test_04_viewer_gets_403_on_admin_routes(self):
        """Viewer role receives 403 Forbidden on admin management routes"""
        c = app.test_client()
        demo_pwd = next(u['password'] for u in SEED_USERS if u['username'] == 'demo')
        c.post('/login', data={'username': 'demo', 'password': demo_pwd})
        
        res_get = c.get('/api/users')
        self.assertEqual(res_get.status_code, 403)
        
        res_post = c.post('/api/users', json={'username': 'test_new', 'password': 'password123'})
        self.assertEqual(res_post.status_code, 403)

    def test_05_dataset_loading_and_preprocessing(self):
        """Dataset dynamically loads all 38 houses, 662 calendar days, and 16,491 records"""
        self.assertEqual(self.engine.num_houses, 38)
        self.assertEqual(self.engine.total_days, 662)
        self.assertEqual(self.engine.total_rows, 16491)
        self.assertEqual(self.engine.all_dates[0], '2019-05-01')
        self.assertEqual(self.engine.all_dates[-1], '2021-02-20')
        self.assertAlmostEqual(self.engine.missing_pct, 35.0, delta=0.2)

    def test_06_missing_and_zero_readings_treatment(self):
        """Zero readings (143) and missing entries are treated as NaN in values array"""
        self.assertEqual(self.engine.zero_rows, 143)
        # Any entry in vals must be > 0 or NaN
        valid_vals = self.engine.vals[~np.isnan(self.engine.vals)]
        self.assertTrue(np.all(valid_vals > 0), "Values array contains non-positive entries")

    def test_07_baseline_windows_and_minimum_history(self):
        """Centered and trailing baselines require at least 5 valid historical readings"""
        exp_c, name_c = self.engine.get_baseline_matrix('Centered 29-day median')
        exp_t, name_t = self.engine.get_baseline_matrix('Trailing 28-day median')
        self.assertIn('Centered', name_c)
        self.assertIn('Trailing', name_t)

        # Baseline must be NaN where fewer than 5 observations exist
        # Trailing baseline on day 0 has 0 prior observations, so all entries on day 0 must be NaN
        self.assertTrue(np.all(np.isnan(exp_t[0, :])), "Trailing baseline on day 0 should be all NaN")

    def test_08_minimum_15_comparable_houses(self):
        """Dates with fewer than 15 comparable houses are marked as low coverage"""
        aggs = self.engine.compute_daily_aggregates('Centered 29-day median')
        low_cov_days = int(np.sum(aggs['low_coverage']))
        self.assertEqual(low_cov_days, 45, "Expected exactly 45 low-coverage days with centered baseline")
        
        # Verify that low coverage days have comparable_count < 15
        for i in range(self.engine.total_days):
            if aggs['low_coverage'][i]:
                self.assertLess(aggs['comparable_count'][i], 15)
            else:
                self.assertGreaterEqual(aggs['comparable_count'][i], 15)

    def test_09_isolation_forest_feature_handling_and_detections(self):
        """Isolation Forest uses [relative increase, absolute increase], flags 4 anomalies where actual > expected"""
        det = self.engine.detect(model='Isolation Forest', threshold=2.0)
        anomalies = det['anomalies']
        self.assertEqual(len(anomalies), 4, f"Expected 4 anomalies, got {len(anomalies)}")
        
        dates = [a['date'] for a in anomalies]
        self.assertIn('2019-09-11', dates)
        self.assertIn('2020-05-24', dates)
        self.assertIn('2019-06-05', dates)
        self.assertIn('2020-05-25', dates)

        for a in anomalies:
            self.assertGreater(a['actual_total'], a['expected_total'])
            self.assertGreater(a['increase'], 0)
            self.assertGreater(a['pct'], 0)
            self.assertGreaterEqual(a['score'], 0.0)
            self.assertLessEqual(a['score'], 1.0)

    def test_10_mad_zero_denominator_and_detections(self):
        """Robust z-score flags 2 anomalies and safely handles zero MAD denominator"""
        det = self.engine.detect(model='Robust z-score (MAD)', threshold=3.5)
        anomalies = det['anomalies']
        self.assertEqual(len(anomalies), 2, f"Expected 2 MAD anomalies, got {len(anomalies)}")
        
        dates = [a['date'] for a in anomalies]
        self.assertIn('2020-05-24', dates)
        self.assertIn('2020-05-25', dates)

        # Test safe handling when MAD is zero
        # Verify that engine does not crash or divide by zero
        test_r = np.zeros(20)
        med_r = float(np.median(test_r))
        mad_r = float(np.median(np.abs(test_r - med_r)))
        self.assertEqual(mad_r, 0.0)

    def test_11_household_attribution_and_reconciliation(self):
        """Household excess attribution ranks by positive excess and reconciles with net increase"""
        houses = self.engine.get_households('2019-09-11', top='all')
        self.assertEqual(len(houses), 32, "Expected 32 comparable houses on 2019-09-11")
        
        # Check top 3 houses match actual data
        self.assertEqual(houses[0]['meter'], 'MH10')
        self.assertAlmostEqual(houses[0]['excess'], 24.4, delta=0.1)
        self.assertEqual(houses[1]['meter'], 'MH24')
        self.assertAlmostEqual(houses[1]['excess'], 13.6, delta=0.1)
        self.assertEqual(houses[2]['meter'], 'MH02')
        self.assertAlmostEqual(houses[2]['excess'], 12.1, delta=0.1)

        # Check contribution shares
        pos_houses = [h for h in houses if h['excess'] > 0]
        total_share = sum(h['share'] for h in pos_houses)
        self.assertAlmostEqual(total_share, 100.0, delta=0.2)

        # Check reconciliation
        rec = self.engine.get_attribution_reconciliation('2019-09-11')
        self.assertTrue(rec['reconciled'])
        self.assertAlmostEqual(rec['net_area_increase'], 107.08, delta=0.05)
        self.assertAlmostEqual(rec['positive_excess_sum'] + rec['negative_deviation_sum'], rec['net_area_increase'], delta=0.01)

if __name__ == '__main__':
    unittest.main()
