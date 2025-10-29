from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime
import threading
import time
from flask_sqlalchemy import SQLAlchemy
import pymysql

# --- Initialize MySQL driver ---
pymysql.install_as_MySQLdb()

# --- Flask App Config ---
app = Flask(__name__)
app.secret_key = "secret123"

# --- Database Configuration (Railway) ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:mmIKdfqjQcxrzyVIazmqfjpEzoiCvvZf@shortline.proxy.rlwy.net:47220/railway'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- ACTIVE TIMERS TRACKER ---
active_timers = {}

# --- Utility Function for DB Cursor ---
def get_cursor():
    connection = db.engine.raw_connection()
    return connection, connection.cursor(pymysql.cursors.DictCursor)

# --- ROOT REDIRECT ---
@app.route("/")
def home():
    return redirect(url_for('login'))

# --- LOGIN PAGE + FUNCTION ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        connection, cursor = get_cursor()
        cursor.execute("SELECT * FROM users WHERE BINARY username=%s AND BINARY password=%s", (username, password))
        user = cursor.fetchone()
        cursor.close()
        connection.close()

        if user:
            if user['username'] != 'admin' and user['time_remaining'] <= 0:
                flash("Your account has no remaining time. Contact admin.", "danger")
                return redirect(url_for('login'))

            session['username'] = user['username']
            session['user_id'] = user['id']

            if username == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                start_timer(user['id'])
                flash("Login successful!", "success")
                return redirect(url_for('user_dashboard'))
        else:
            flash("Invalid username or password", "danger")
    return render_template('login.html')

# --- REGISTER PAGE ---
@app.route("/register", methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        connection, cursor = get_cursor()
        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        existing = cursor.fetchone()
        if existing:
            flash("Username already exists", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for('register'))

        cursor.execute("INSERT INTO users (username, password, time_remaining, last_login) VALUES (%s, %s, 0, NOW())",
                       (username, password))
        connection.commit()
        cursor.close()
        connection.close()
        flash("Registration successful! Please login.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')

# --- TIMER THREAD FUNCTION ---
def countdown_timer(user_id):
    while user_id in active_timers:
        connection, cursor = get_cursor()
        cursor.execute("SELECT time_remaining FROM users WHERE id=%s", (user_id,))
        user = cursor.fetchone()
        if not user:
            cursor.close()
            connection.close()
            break

        time_left = user['time_remaining']
        if time_left <= 0:
            stop_timer(user_id)
            break

        new_time = max(0, time_left - 1)
        cursor.execute("UPDATE users SET time_remaining=%s WHERE id=%s", (new_time, user_id))
        connection.commit()
        cursor.close()
        connection.close()

        if new_time <= 300:
            print(f"⚠️ Warning: User {user_id} has less than 5 minutes remaining.")

        time.sleep(1)

def start_timer(user_id):
    if user_id not in active_timers:
        active_timers[user_id] = True
        threading.Thread(target=countdown_timer, args=(user_id,), daemon=True).start()

def stop_timer(user_id):
    if user_id in active_timers:
        del active_timers[user_id]

# --- ADMIN DASHBOARD ---
@app.route('/admin')
def admin_dashboard():
    if 'username' not in session or session['username'] != 'admin':
        return redirect(url_for('login'))

    connection, cursor = get_cursor()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    cursor.close()
    connection.close()

    return render_template('admin_dashboard.html', users=users, admin=session['username'])

# --- USER DASHBOARD ---
@app.route('/user')
def user_dashboard():
    if 'username' not in session or session['username'] == 'admin':
        return redirect(url_for('login'))

    user_id = session['user_id']
    connection, cursor = get_cursor()
    cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    connection.close()

    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('login'))

    return render_template('user_dashboard.html', user=user)

# --- LOGOUT ---
@app.route('/logout')
def logout():
    if 'user_id' in session:
        stop_timer(session['user_id'])
    session.clear()
    flash("Logged out successfully!", "info")
    return redirect(url_for('login'))

# --- Remaining admin functions (add/update/delete/set_time) remain unchanged ---
# --- CREATE TABLE IF NOT EXISTS ---
with app.app_context():
    connection, cursor = get_cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL,
            time_remaining INT DEFAULT 0,
            last_login DATETIME NULL
        )
    """)
    connection.commit()
    cursor.close()
    connection.close()
    print("✅ Table 'users' verified or created successfully")

# --- RUN APP ---
if __name__ == '__main__':
    app.run(debug=True)
