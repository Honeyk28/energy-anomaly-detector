import os
import sqlite3
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest

DB_PATH = os.path.join(os.path.dirname(__file__), 'app.db')

class AnalyticsEngine:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._cache = {}
        self.load_data()

    def load_data(self):
        conn = sqlite3.connect(self.db_path)
        try:
            self.raw_df = pd.read_sql_query("SELECT meter, date, kwh FROM readings ORDER BY date, meter", conn)
        finally:
            conn.close()

        if self.raw_df.empty:
            csv_path = os.path.join(os.path.dirname(__file__), 'data', 'SM_Cleaned_Data_MH_Aggregated.csv')
            if os.path.exists(csv_path):
                self.raw_df = pd.read_csv(csv_path)
                self.raw_df.columns = ['meter', 'date', 'kwh']

        self.total_rows = len(self.raw_df)
        self.zero_rows = int((self.raw_df['kwh'] == 0).sum())
        
        # Valid readings: kwh > 0
        valid_df = self.raw_df[self.raw_df['kwh'] > 0].copy()
        valid_df['date'] = valid_df['date'].astype(str).str.strip()
        valid_df['meter'] = valid_df['meter'].astype(str).str.strip()
        
        # Unique meters sorted
        self.meters = sorted(valid_df['meter'].unique().tolist())
        self.num_houses = len(self.meters)
        self.meter_to_idx = {m: i for i, m in enumerate(self.meters)}
        
        # Calendar date range
        min_date = valid_df['date'].min()
        max_date = valid_df['date'].max()
        self.all_dates = pd.date_range(min_date, max_date, freq='D').strftime('%Y-%m-%d').tolist()
        self.total_days = len(self.all_dates)
        self.date_to_idx = {d: i for i, d in enumerate(self.all_dates)}
        
        # 2D values array: shape (total_days, num_houses)
        self.vals = np.full((self.total_days, self.num_houses), np.nan)
        for _, row in valid_df.iterrows():
            d = row['date']
            m = row['meter']
            if d in self.date_to_idx and m in self.meter_to_idx:
                self.vals[self.date_to_idx[d], self.meter_to_idx[m]] = float(row['kwh'])

        # Precompute baselines
        self.expected_centered = self._compute_centered_median()
        self.expected_trailing = self._compute_trailing_median()

    def _compute_centered_median(self):
        """Centered 29-day median: [d-14, d+14] excluding day d, require >= 5 valid readings"""
        N, M = self.vals.shape
        exp = np.full_like(self.vals, np.nan)
        for i in range(N):
            start = max(0, i - 14)
            end = min(N, i + 15)
            w1 = self.vals[start:i, :] if i > start else np.empty((0, M))
            w2 = self.vals[i+1:end, :] if i+1 < end else np.empty((0, M))
            w = np.vstack([w1, w2])
            counts = np.sum(~np.isnan(w), axis=0)
            for m in range(M):
                if counts[m] >= 5:
                    exp[i, m] = np.nanmedian(w[:, m])
        return exp

    def _compute_trailing_median(self):
        """Trailing 28-day median: [d-28, d-1], require >= 5 valid readings"""
        N, M = self.vals.shape
        exp = np.full_like(self.vals, np.nan)
        for i in range(N):
            start = max(0, i - 28)
            if i > start:
                w = self.vals[start:i, :]
                counts = np.sum(~np.isnan(w), axis=0)
                for m in range(M):
                    if counts[m] >= 5:
                        exp[i, m] = np.nanmedian(w[:, m])
        return exp

    def get_baseline_matrix(self, baseline_name):
        if 'trailing' in str(baseline_name).lower():
            return self.expected_trailing, "Trailing 28-day median"
        return self.expected_centered, "Centered 29-day median"

    def compute_daily_aggregates(self, baseline_name="Centered 29-day median"):
        cache_key = f"agg_{baseline_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        exp, norm_name = self.get_baseline_matrix(baseline_name)
        N = self.total_days
        
        actual_total = np.zeros(N)
        expected_total = np.zeros(N)
        comparable_count = np.zeros(N, dtype=int)
        
        for i in range(N):
            mask = (~np.isnan(self.vals[i, :])) & (~np.isnan(exp[i, :]))
            cnt = int(np.sum(mask))
            comparable_count[i] = cnt
            if cnt > 0:
                actual_total[i] = float(np.sum(self.vals[i, mask]))
                expected_total[i] = float(np.sum(exp[i, mask]))
        
        increase = actual_total - expected_total
        pct = np.zeros(N)
        valid_exp = expected_total > 0
        pct[valid_exp] = increase[valid_exp] / expected_total[valid_exp]
        low_coverage = comparable_count < 15

        res = {
            'actual_total': actual_total,
            'expected_total': expected_total,
            'increase': increase,
            'pct': pct,
            'comparable_count': comparable_count,
            'low_coverage': low_coverage,
            'baseline_matrix': exp,
            'baseline_name': norm_name
        }
        self._cache[cache_key] = res
        return res

    def detect(self, model="Isolation Forest", threshold=None, baseline="Centered 29-day median",
               train_from=None, train_to=None, from_date=None, to_date=None):
        
        # Set defaults
        model_name = "Robust z-score (MAD)" if "robust" in str(model).lower() or "z-score" in str(model).lower() or "mad" in str(model).lower() else "Isolation Forest"
        
        if threshold is None or threshold == '' or threshold == '[threshold]':
            threshold = 3.5 if model_name == "Robust z-score (MAD)" else 2.0
        else:
            try:
                threshold = float(threshold)
            except (ValueError, TypeError):
                threshold = 3.5 if model_name == "Robust z-score (MAD)" else 2.0

        if not train_from or train_from not in self.date_to_idx:
            train_from = self.all_dates[0]
        if not train_to or train_to not in self.date_to_idx:
            train_to = self.all_dates[-1]

        if not from_date or from_date not in self.date_to_idx:
            from_date = self.all_dates[0]
        if not to_date or to_date not in self.date_to_idx:
            to_date = self.all_dates[-1]

        cache_key = f"detect_{model_name}_{threshold}_{baseline}_{train_from}_{train_to}_{from_date}_{to_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        aggs = self.compute_daily_aggregates(baseline)
        actual = aggs['actual_total']
        expected = aggs['expected_total']
        increase = aggs['increase']
        pct = aggs['pct']
        comparable_count = aggs['comparable_count']
        low_coverage = aggs['low_coverage']

        train_s = self.date_to_idx[train_from]
        train_e = self.date_to_idx[train_to]
        if train_s > train_e:
            train_s, train_e = train_e, train_s

        # Training indices: in window and not low_coverage
        train_indices = [i for i in range(train_s, train_e + 1) if not low_coverage[i]]

        N = self.total_days
        flagged = np.zeros(N, dtype=bool)
        scores = np.zeros(N)

        if len(train_indices) >= 10:
            train_r = pct[train_indices]
            train_inc = increase[train_indices]

            if model_name == "Robust z-score (MAD)":
                med_r = float(np.median(train_r))
                mad_r = float(np.median(np.abs(train_r - med_r)))
                scale = 1.4826 * mad_r if mad_r > 1e-8 else 1.0

                for i in range(N):
                    if not low_coverage[i]:
                        z = (pct[i] - med_r) / scale
                        # Score mapped to 0..1 range with 0.8 around threshold
                        s = 1.0 / (1.0 + np.exp(-(z - threshold)))
                        scores[i] = round(float(s), 2)
                        if z > threshold and pct[i] > 0:
                            flagged[i] = True
            else:
                # Isolation Forest
                contamination = max(0.001, min(0.5, threshold / 100.0))
                X_train = np.column_stack([train_r, train_inc])
                clf = IsolationForest(contamination=contamination, random_state=42)
                clf.fit(X_train)

                # Score all valid dates
                valid_all = [i for i in range(N) if not low_coverage[i]]
                if valid_all:
                    X_all = np.column_stack([pct[valid_all], increase[valid_all]])
                    preds = clf.predict(X_all)
                    # Decision function is negative for outliers; lower = more anomalous
                    dec = clf.decision_function(X_all)
                    # Convert to anomaly score between 0 and 1
                    # min dec -> highest anomaly score
                    min_d = dec.min()
                    max_d = dec.max()
                    rng = max_d - min_d if (max_d - min_d) > 1e-6 else 1.0
                    norm_scores = 1.0 - (dec - min_d) / rng

                    for idx, i in enumerate(valid_all):
                        scores[i] = round(float(norm_scores[idx]), 2)
                        if preds[idx] == -1 and pct[i] > 0:
                            flagged[i] = True

        # View slice from from_date to to_date
        disp_s = self.date_to_idx[from_date]
        disp_e = self.date_to_idx[to_date]
        if disp_s > disp_e:
            disp_s, disp_e = disp_e, disp_s

        series = []
        for i in range(disp_s, disp_e + 1):
            series.append({
                'date': self.all_dates[i],
                'actual_total': round(float(actual[i]), 1),
                'expected_total': round(float(expected[i]), 1),
                'comparable_count': int(comparable_count[i]),
                'flagged': bool(flagged[i]),
                'low_coverage': bool(low_coverage[i])
            })

        # List of anomalies across scanned period
        anomalies = []
        for i in range(disp_s, disp_e + 1):
            if flagged[i]:
                anomalies.append({
                    'date': self.all_dates[i],
                    'actual_total': round(float(actual[i]), 1),
                    'expected_total': round(float(expected[i]), 1),
                    'increase': round(float(increase[i]), 2),
                    'raw_increase': float(increase[i]),
                    'pct': round(float(pct[i] * 100), 1),
                    'score': float(scores[i])
                })

        # Sort anomalies by score descending
        anomalies.sort(key=lambda x: (x['score'], x['increase']), reverse=True)

        scanned_count = (disp_e - disp_s + 1)
        low_cov_days = int(np.sum(low_coverage[disp_s:disp_e + 1]))

        result = {
            'series': series,
            'anomalies': anomalies,
            'summary': {
                'model': model_name,
                'scanned': scanned_count,
                'flagged': len(anomalies),
                'threshold': threshold,
                'low_coverage_days': low_cov_days
            }
        }
        self._cache[cache_key] = result
        return result

    def get_households(self, date, baseline="Centered 29-day median", rank_by="excess", top="all"):
        if date not in self.date_to_idx:
            # Fallback to first date or an anomaly date
            date = self.all_dates[0]

        d_idx = self.date_to_idx[date]
        exp, _ = self.get_baseline_matrix(baseline)

        mask = (~np.isnan(self.vals[d_idx, :])) & (~np.isnan(exp[d_idx, :]))
        comp_indices = np.where(mask)[0]

        rows = []
        pos_excess_sum = 0.0
        
        items = []
        for m_idx in comp_indices:
            act = float(self.vals[d_idx, m_idx])
            expected = float(exp[d_idx, m_idx])
            excess = act - expected
            if excess > 0:
                pos_excess_sum += excess
            items.append({
                'meter': self.meters[m_idx],
                'actual': act,
                'expected': expected,
                'excess': excess
            })

        # Calculate share
        for item in items:
            exc = item['excess']
            if pos_excess_sum > 0 and exc > 0:
                share = (exc / pos_excess_sum) * 100.0
            else:
                share = 0.0
            item['share'] = share

        # Sort
        if rank_by == 'share':
            items.sort(key=lambda x: x['share'], reverse=True)
        else:
            items.sort(key=lambda x: x['excess'], reverse=True)

        # Reconcile rounding so sum(excess) equals target increase exactly
        aggs = self.compute_daily_aggregates(baseline)
        target_increase = round(float(aggs['increase'][d_idx]), 2)
        excess_sum = round(sum(round(item['excess'], 2) for item in items), 2)
        diff = round(target_increase - excess_sum, 2)
        if abs(diff) > 0 and len(items) > 0:
            items[0]['excess'] = items[0]['excess'] + diff

        # Apply rank and format
        for idx, item in enumerate(items, start=1):
            rows.append({
                'rank': idx,
                'meter': item['meter'],
                'actual': round(item['actual'], 1),
                'expected': round(item['expected'], 1),
                'excess': round(item['excess'], 2),
                'raw_excess': item['excess'],
                'share': round(item['share'], 1)
            })

        if str(top).isdigit():
            rows = rows[:int(top)]
        elif str(top).lower() == '10':
            rows = rows[:10]
        elif str(top).lower() == '20':
            rows = rows[:20]

        return rows

    def get_house_history(self, meter, date, baseline="Centered 29-day median"):
        """Get actual vs expected for date - 15 .. + 15 days for specified house"""
        if meter not in self.meter_to_idx:
            return {'meter': meter, 'history': []}

        m_idx = self.meter_to_idx[meter]
        exp, _ = self.get_baseline_matrix(baseline)

        if date not in self.date_to_idx:
            date = self.all_dates[0]
        d_idx = self.date_to_idx[date]

        start_idx = max(0, d_idx - 15)
        end_idx = min(self.total_days - 1, d_idx + 15)

        history = []
        for i in range(start_idx, end_idx + 1):
            act = self.vals[i, m_idx]
            expected = exp[i, m_idx]
            history.append({
                'date': self.all_dates[i],
                'actual': round(float(act), 1) if not np.isnan(act) else None,
                'expected': round(float(expected), 1) if not np.isnan(expected) else None,
                'is_target': (i == d_idx)
            })

        actual_at = self.vals[d_idx, m_idx]
        exp_at = exp[d_idx, m_idx]

        return {
            'meter': meter,
            'target_date': date,
            'actual_at_date': round(float(actual_at), 1) if not np.isnan(actual_at) else None,
            'expected_at_date': round(float(exp_at), 1) if not np.isnan(exp_at) else None,
            'baseline_source': 'Own history',
            'history': history
        }

    def get_overview(self):
        det = self.detect()
        aggs = self.compute_daily_aggregates()

        missing_pct = 1.0 - (self.total_rows / (self.num_houses * self.total_days))

        anomalies = det['anomalies']
        top_anomaly_date = anomalies[0]['date'] if anomalies else self.all_dates[0]
        top_anomaly = anomalies[0] if anomalies else None

        top_houses = self.get_households(top_anomaly_date, top=5)

        kpis = {
            'houses': self.num_houses,
            'period_start': self.all_dates[0],
            'period_end': self.all_dates[-1],
            'missing_pct': round(missing_pct * 100, 1),
            'anomalies_flagged': len(anomalies)
        }

        return {
            'kpis': kpis,
            'series': det['series'],
            'anomalies': anomalies,
            'top_anomaly': top_anomaly,
            'top_houses': top_houses
        }

    def get_method_stats(self):
        missing_pct = 1.0 - (self.total_rows / (self.num_houses * self.total_days))
        
        per_meter = []
        for m in self.meters:
            m_idx = self.meter_to_idx[m]
            meter_vals = self.vals[:, m_idx]
            valid_mask = ~np.isnan(meter_vals)
            days_with_data = int(np.sum(valid_mask))
            if days_with_data > 0:
                valid_indices = np.where(valid_mask)[0]
                first_date = self.all_dates[valid_indices[0]]
                last_date = self.all_dates[valid_indices[-1]]
            else:
                first_date = "N/A"
                last_date = "N/A"
            cov_pct = round((days_with_data / self.total_days) * 100, 1)
            per_meter.append({
                'meter': m,
                'first_date': first_date,
                'last_date': last_date,
                'days_with_data': days_with_data,
                'coverage_pct': cov_pct
            })

        dataset = {
            'houses': self.num_houses,
            'rows': self.total_rows,
            'reading_interval': 'Daily',
            'period': f"{self.all_dates[0]} to {self.all_dates[-1]}",
            'zero_count': self.zero_rows,
            'missing_pct': round(missing_pct * 100, 1),
            'source': 'CEEW smart meter data, doi:10.7910/DVN/GOCHJH, CC0'
        }

        return {
            'dataset': dataset,
            'coverage': per_meter
        }

engine = AnalyticsEngine()
