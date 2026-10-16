import os
import secrets
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from dotenv import load_dotenv

load_dotenv()

from db import (
    init_db, get_user_by_id, get_user_by_username, get_all_users,
    create_user, update_user_status, update_user_password, delete_user,
    record_login_attempt, is_username_locked, get_recent_logins, update_last_login
)
from engine import engine

app = Flask(__name__)

# Secret key handling
secret_key = os.getenv('SECRET_KEY')
if not secret_key:
    secret_key = secrets.token_hex(32)
app.secret_key = secret_key

# Cookie settings
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    try:
        user = get_user_by_id(int(user_id))
        return user
    except Exception:
        return None

@login_manager.unauthorized_handler
def unauthorized():
    user_id = session.get('_user_id')
    if user_id:
        user = get_user_by_id(int(user_id))
        if user and not user.is_active:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Access has been disabled. Contact an administrator.'}), 401
            return render_template('login.html', error='Access has been disabled. Contact an administrator.'), 401
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Unauthorized. Please sign in.'}), 401
    return redirect(url_for('login'))

@app.before_request
def check_user_active_status():
    user_id = session.get('_user_id')
    if user_id:
        user = get_user_by_id(int(user_id))
        if not user or not user.is_active:
            logout_user()
            session.clear()
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Access has been disabled. Contact an administrator.'}), 401
            return render_template('login.html', error='Access has been disabled. Contact an administrator.'), 401

# ==========================================
# AUTH ROUTES
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated and current_user.is_active:
        return redirect(url_for('index'))

    error = None
    username = ''
    ip = request.remote_addr or '127.0.0.1'

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # Throttle check: 5 failed attempts in last 60s
        if is_username_locked(username):
            error = 'Too many failed sign-in attempts. Account temporarily locked for 60 seconds.'
        else:
            user = get_user_by_username(username)
            if not user or not user.check_password(password):
                record_login_attempt(username, False, ip)
                error = 'Invalid username or password.'
            elif not user.is_active:
                record_login_attempt(username, False, ip)
                error = 'Access has been disabled. Contact an administrator.'
            else:
                record_login_attempt(username, True, ip)
                update_last_login(user.id)
                login_user(user)
                next_page = request.args.get('next')
                if next_page and next_page.startswith('/'):
                    return redirect(next_page)
                return redirect(url_for('index'))

    return render_template('login.html', error=error, username=username)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('app.html')

# ==========================================
# ANALYTICS API ROUTES
# ==========================================

@app.route('/api/overview')
@login_required
def api_overview():
    try:
        data = engine.get_overview()
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/detect')
@login_required
def api_detect():
    try:
        model = request.args.get('model', 'Isolation Forest')
        threshold = request.args.get('threshold')
        baseline = request.args.get('baseline', 'Centered 29-day median')
        train_from = request.args.get('train_from')
        train_to = request.args.get('train_to')
        from_date = request.args.get('from')
        to_date = request.args.get('to')

        data = engine.detect(
            model=model,
            threshold=threshold,
            baseline=baseline,
            train_from=train_from,
            train_to=train_to,
            from_date=from_date,
            to_date=to_date
        )
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/households')
@login_required
def api_households():
    try:
        date = request.args.get('date')
        baseline = request.args.get('baseline', 'Centered 29-day median')
        rank_by = request.args.get('rank_by', 'excess')
        top = request.args.get('top', 'all')

        rows = engine.get_households(date=date, baseline=baseline, rank_by=rank_by, top=top)
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/house')
@login_required
def api_house():
    try:
        meter = request.args.get('meter')
        date = request.args.get('date')
        baseline = request.args.get('baseline', 'Centered 29-day median')

        if not meter or not date:
            return jsonify({'error': 'meter and date parameters required'}), 400

        data = engine.get_house_history(meter=meter, date=date, baseline=baseline)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/method')
@login_required
def api_method():
    try:
        data = engine.get_method_stats()
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==========================================
# USER MANAGEMENT (ADMIN ONLY)
# ==========================================

def admin_required():
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({'error': 'Admin permissions required'}), 403
    return None

@app.route('/api/users', methods=['GET', 'POST'])
@login_required
def api_users():
    err = admin_required()
    if err:
        return err

    if request.method == 'GET':
        users = get_all_users()
        return jsonify(users)

    if request.method == 'POST':
        data = request.get_json() or {}
        username = data.get('username', '').strip()
        display_name = data.get('display_name', '').strip()
        role = data.get('role', 'viewer').strip()
        password = data.get('password', '')

        if not username or not display_name or not password:
            return jsonify({'error': 'Username, display name, and password are required.'}), 400

        try:
            user_id = create_user(username, display_name, role, password)
            return jsonify({'success': True, 'id': user_id}), 201
        except Exception as e:
            return jsonify({'error': str(e)}), 400

@app.route('/api/users/<int:user_id>', methods=['PATCH', 'DELETE'])
@login_required
def api_user_modify(user_id):
    err = admin_required()
    if err:
        return err

    if request.method == 'PATCH':
        data = request.get_json() or {}
        try:
            if 'is_active' in data:
                update_user_status(user_id, bool(data['is_active']), current_user.id)
            if 'password' in data and data['password']:
                update_user_password(user_id, data['password'])
            return jsonify({'success': True})
        except ValueError as ve:
            return jsonify({'error': str(ve)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    if request.method == 'DELETE':
        try:
            delete_user(user_id, current_user.id)
            return jsonify({'success': True})
        except ValueError as ve:
            return jsonify({'error': str(ve)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route('/api/users/log')
@login_required
def api_user_log():
    err = admin_required()
    if err:
        return err
    logs = get_recent_logins(limit=20)
    return jsonify(logs)

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    import socket
    def is_port_free(p):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', p)) != 0

    if not is_port_free(port):
        print(f"\n[Notice] Port {port} is in use (macOS AirPlay Receiver default).")
        alt_port = 5001 if port == 5000 else port + 1
        print(f"[Notice] Starting server on port {alt_port} -> http://localhost:{alt_port}\n")
        port = alt_port

    app.run(host='0.0.0.0', port=port, debug=False)
