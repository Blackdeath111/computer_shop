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

# --- LOGIN PAGE + FUNCTION ---
@app.route('/', methods=['GET', 'POST'])
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

# --- LOGOUT ---
@app.route('/logout')
def logout():
    if 'user_id' in session:
        stop_timer(session['user_id'])
    session.clear()
    flash("Logged out successfully!", "info")
    return redirect(url_for('login'))

# --- ADD USER ---
@app.route('/add_user', methods=['POST'])
def add_user():
    username = request.form['username']
    password = request.form['password']

    if username == 'admin':
        flash("Cannot create another admin!", "danger")
        return redirect(url_for('admin_dashboard'))

    connection, cursor = get_cursor()
    cursor.execute("INSERT INTO users (username, password, time_remaining, last_login) VALUES (%s, %s, 0, NOW())",
                   (username, password))
    connection.commit()
    cursor.close()
    connection.close()

    flash("User added successfully!", "success")
    return redirect(url_for('admin_dashboard'))

# --- UPDATE USER ---
@app.route('/update_user/<int:user_id>', methods=['POST'])
def update_user(user_id):
    username = request.form['username']
    password = request.form['password']

    connection, cursor = get_cursor()
    cursor.execute("SELECT username FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()

    if not user or user['username'] == 'admin':
        flash("Cannot modify admin account.", "warning")
        cursor.close()
        connection.close()
        return redirect(url_for('admin_dashboard'))

    cursor.execute("UPDATE users SET username=%s, password=%s WHERE id=%s", (username, password, user_id))
    connection.commit()
    cursor.close()
    connection.close()

    flash("User updated successfully!", "success")
    return redirect(url_for('admin_dashboard'))

# --- SET / ADD / SUBTRACT / SAVE TIME (admin side) ---
@app.route('/set_time/<int:user_id>', methods=['POST'])
def set_time(user_id):
    connection, cursor = get_cursor()
    cursor.execute("SELECT username, time_remaining FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()

    if not user or user['username'] == 'admin':
        cursor.close()
        connection.close()
        return jsonify({"success": False, "message": "Cannot modify admin time."}), 400

    hours = int(request.form.get('hours', 0))
    minutes = int(request.form.get('minutes', 0))
    total_seconds = (hours * 60 + minutes) * 60
    action = request.form.get('action')

    new_time = user['time_remaining']
    msg = ""

    if action == 'add':
        new_time += total_seconds
        msg = "Time added successfully!"
    elif action == 'subtract':
        new_time = max(0, new_time - total_seconds)
        msg = "Time subtracted successfully!"
    elif action == 'set':
        new_time = total_seconds
        msg = "Time saved successfully!"
    else:
        cursor.close()
        connection.close()
        return jsonify({"success": False, "message": "Invalid action."}), 400

    cursor.execute("UPDATE users SET time_remaining=%s WHERE id=%s", (new_time, user_id))
    connection.commit()
    cursor.close()
    connection.close()

    hh = new_time // 3600
    mm = (new_time % 3600) // 60
    ss = new_time % 60
    return jsonify({"success": True, "message": msg, "new_time": f"{hh:02d}h {mm:02d}m {ss:02d}s"})

# --- DELETE USER ---
@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    connection, cursor = get_cursor()
    cursor.execute("SELECT username FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()

    if not user or user['username'] == 'admin':
        flash("Cannot delete admin!", "warning")
        cursor.close()
        connection.close()
        return redirect(url_for('admin_dashboard'))

    cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
    connection.commit()
    cursor.close()
    connection.close()

    flash("User deleted successfully!", "info")
    return redirect(url_for('admin_dashboard'))

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

# --- UPDATE REMAINING TIME (AJAX) ---
@app.route('/update_remaining_time/<int:user_id>', methods=['POST'])
def update_remaining_time(user_id):
    data = request.get_json()
    seconds = data.get('seconds', 0)
    connection, cursor = get_cursor()
    cursor.execute("UPDATE users SET time_remaining=%s WHERE id=%s", (seconds, user_id))
    connection.commit()
    cursor.close()
    connection.close()
    return jsonify({"success": True})

# --- GET USER TIME ---
@app.route('/get_user_time/<int:user_id>')
def get_user_time(user_id):
    connection, cursor = get_cursor()
    cursor.execute("SELECT username, time_remaining FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    connection.close()

    if not user:
        return jsonify({"success": False})
    return jsonify({"success": True, "time_remaining": user['time_remaining']})

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
