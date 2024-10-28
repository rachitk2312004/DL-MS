from flask import Flask, send_file, render_template, request, redirect, session, flash, url_for
import sqlite3
import hashlib
from datetime import datetime
import pandas as pd
import io

app = Flask(__name__)
app.secret_key = 'super_secret_key'

# Database Initialization
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, uid TEXT, email TEXT UNIQUE, password TEXT, role TEXT, coordinator_unique_id TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS duty_leave 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, date TEXT, unique_key TEXT, status TEXT, student_name TEXT, student_uid TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS events 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, coordinator_id INTEGER, event_name TEXT, event_type TEXT, venue TEXT, timings TEXT, date TEXT, max_students INTEGER, registration_count INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS event_registrations
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER, user_id INTEGER)''')
    conn.commit()
    conn.close()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'xls', 'xlsx'}

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

@app.route('/')
def index():
    if 'user_id' in session:
        if session['role'] == 'student':
            return redirect(url_for('student_dashboard'))
        elif session['role'] == 'coordinator':
            return redirect(url_for('coordinator_dashboard'))
    return render_template('index.html')

@app.route('/register_student', methods=['GET', 'POST'])
def register_student():
    if request.method == 'POST':
        name = request.form['name']
        uid = request.form['uid']
        email = request.form['email']
        password = hash_password(request.form['password'])
        
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("INSERT INTO users (name, uid, email, password, role) VALUES (?, ?, ?, ?, ?)",
                  (name, uid, email, password, 'student'))
        conn.commit()
        conn.close()

        flash("Student registration successful! Please login.", "success")
        return redirect(url_for('login_student'))
    return render_template('register_student.html')

@app.route('/register_coordinator', methods=['GET', 'POST'])
def register_coordinator():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = hash_password(request.form['password'])
        coordinator_unique_id = request.form['unique_id']
        
        allowed_ids = ["COORD123", "COORD456"]
        if coordinator_unique_id not in allowed_ids:
            flash("Invalid Coordinator Unique ID", "danger")
            return render_template('register_coordinator.html')

        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("INSERT INTO users (name, email, password, role, coordinator_unique_id) VALUES (?, ?, ?, ?, ?)",
                  (name, email, password, 'coordinator', coordinator_unique_id))
        conn.commit()
        conn.close()

        flash("Coordinator registration successful! Please login.", "success")
        return redirect(url_for('login_coordinator'))
    return render_template('register_coordinator.html')

@app.route('/login_student', methods=['GET', 'POST'])
def login_student():
    if request.method == 'POST':
        email = request.form['email']
        password = hash_password(request.form['password'])

        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = ? AND password = ? AND role = 'student'", (email, password))
        user = c.fetchone()
        conn.close()

        if user:
            session['user_id'] = user[0]
            session['name'] = user[1]
            session['uid'] = user[2]
            session['role'] = user[5]
            return redirect(url_for('student_dashboard'))
        else:
            flash("Invalid email or password", "danger")
    return render_template('login_student.html')

@app.route('/login_coordinator', methods=['GET', 'POST'])
def login_coordinator():
    if request.method == 'POST':
        email = request.form['email']
        password = hash_password(request.form['password'])

        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = ? AND password = ? AND role = 'coordinator'", (email, password))
        user = c.fetchone()
        conn.close()

        if user:
            session['user_id'] = user[0]
            session['name'] = user[1]
            session['role'] = user[5]
            return redirect(url_for('coordinator_dashboard'))
        else:
            flash("Invalid email or password", "danger")
    return render_template('login_coordinator.html')

@app.route('/student_dashboard', methods=['GET'])
def student_dashboard():
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('index'))
    name = session['name']
    uid = session['uid']
    return render_template('student_dashboard.html', name=name, uid=uid)
@app.route('/apply_duty_leave', methods=['GET', 'POST'])
def apply_duty_leave():
    if 'user_id' not in session:
        return redirect(url_for('login_student'))

    user_id = session['user_id']
    name = session['name']
    uid = session['uid']

    conn = sqlite3.connect('users.db')
    c = conn.cursor()

    if request.method == 'POST':
        date = request.form['date']
        unique_key = request.form['unique_key']

        # Check if a leave is already applied for this date
        c.execute("SELECT * FROM duty_leave WHERE user_id = ? AND date = ?", (user_id, date))
        existing_leave = c.fetchone()

        if existing_leave:
            flash("Leave already applied for this date.", "warning")
        else:
            c.execute("INSERT INTO duty_leave (user_id, date, unique_key, status, student_name, student_uid) VALUES (?, ?, ?, ?, ?, ?)",
                      (user_id, date, unique_key, 'Pending', name, uid))
            conn.commit()
            flash("Duty leave application submitted", "info")

    # Retrieve all leave applications for this student
    c.execute("SELECT date, unique_key, status FROM duty_leave WHERE user_id = ?", (user_id,))
    applied_leaves = c.fetchall()
    conn.close()

    return render_template('apply_duty_leave.html', applied_leaves=applied_leaves)


@app.route('/validate_duty_leave', methods=['GET', 'POST'])
def validate_duty_leave():
    if 'user_id' not in session or session['role'] != 'coordinator':
        return redirect(url_for('index'))

    if request.method == 'POST':
        date = request.form['date']
        file = request.files['file']

        # Initialize denied_requests list
        denied_requests = []

        if file and allowed_file(file.filename):
            # Read the Excel file into a DataFrame
            df = pd.read_excel(file)

            # Ensure DataFrame columns match the expected names
            df = df[['name', 'uid', 'unique_key']]  # Adjust based on your Excel structure

            conn = sqlite3.connect('users.db')
            c = conn.cursor()

            # Fetch all duty leave records for the given date
            c.execute("SELECT id, student_name, student_uid, unique_key FROM duty_leave WHERE date = ?", (date,))
            duty_leaves = c.fetchall()

            # Convert duty_leaves into a set of (name, uid, unique_key) for matching
            duty_leave_set = {(leave[1], leave[2], leave[3]) for leave in duty_leaves}

            # Track leaves that need to be granted based on exact match
            to_grant = []

            # Loop through the DataFrame rows to identify matches
            for _, row in df.iterrows():
                key = (row['name'], row['uid'], row['unique_key'])
                if key in duty_leave_set:
                    # Record leaves to be updated as "Granted"
                    to_grant.append(key)
                else:
                    # If there is no match, add this entry to the denied list
                    denied_requests.append(key)

            # Update database statuses
            # First, deny all records for the specified date to reset
            c.execute("""
                UPDATE duty_leave 
                SET status = 'Denied'
                WHERE date = ?""",
                      (date,))

            # Then grant the ones that are in the 'to_grant' list
            for name, uid, unique_key in to_grant:
                c.execute("""
                    UPDATE duty_leave 
                    SET status = 'Granted' 
                    WHERE student_name = ? AND student_uid = ? AND unique_key = ? AND date = ?""",
                          (name, uid, unique_key, date))

            # Commit changes and close connection
            conn.commit()
            conn.close()
            flash("Duty leave applications validated successfully!", "success")
            return redirect(url_for('coordinator_dashboard'))

    return render_template('validate_duty_leave.html')

@app.route('/join_event', methods=['GET', 'POST'])
def join_event():
    if 'user_id' not in session:
        return redirect(url_for('login_student'))

    user_id = session['user_id']
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row  # This allows us to access columns by name
    c = conn.cursor()

    # Select relevant details for each event, including registration status
    c.execute("""
        SELECT events.id, events.event_name, events.event_type, events.venue, events.timings, events.date, 
               events.max_students, events.registration_count, event_registrations.id AS reg_id 
        FROM events 
        LEFT JOIN event_registrations 
        ON events.id = event_registrations.event_id AND event_registrations.user_id = ?
    """, (user_id,))
    
    events = c.fetchall()
    conn.close()

    # Organize events into categories
    past_events, live_events, upcoming_events, participated_events = [], [], [], []
    current_date = datetime.now().date()

    for event in events:
        event_data = {
            "id": event["id"],
            "name": event["event_name"],
            "type": event["event_type"],
            "venue": event["venue"],
            "timings": event["timings"],
            "date": event["date"],
            "max_students": event["max_students"],
            "registration_count": event["registration_count"],
        }
        event_date = datetime.strptime(event["date"], '%Y-%m-%d').date()
        registered = event["reg_id"] is not None  # Check if user is registered

        if registered:
            participated_events.append(event_data)
        elif event_date < current_date:
            past_events.append(event_data)
        elif event_date == current_date:
            live_events.append(event_data)
        else:
            upcoming_events.append(event_data)

    return render_template(
        'join_event.html', 
        upcoming_events=upcoming_events, 
        live_events=live_events, 
        past_events=past_events, 
        participated_events=participated_events
    )
@app.route('/register_event/<int:event_id>', methods=['POST'])
def register_event(event_id):
    # Check if the user is logged in
    if 'user_id' not in session:
        return redirect(url_for('login_student'))

    user_id = session['user_id']

    # Connect to the database
    conn = sqlite3.connect('users.db')
    c = conn.cursor()

    try:
        # Check event capacity and current registrations
        c.execute("SELECT max_students, registration_count FROM events WHERE id = ?", (event_id,))
        event = c.fetchone()

        # If event exists and is full, show an error message
        if event and event[1] >= event[0]:
            flash("Event is full. Unable to register.", "danger")
            return redirect(url_for('join_event'))

        # Register the user for the event
        c.execute("INSERT INTO event_registrations (event_id, user_id) VALUES (?, ?)", (event_id, user_id))
        c.execute("UPDATE events SET registration_count = registration_count + 1 WHERE id = ?", (event_id,))
        
        # Commit changes to the database
        conn.commit()
        
        # Show a success message after successful registration
        flash("Successfully registered for the event!", "success")

    except sqlite3.Error as e:
        # Roll back in case of an error and flash a message
        conn.rollback()
        flash("An error occurred during registration. Please try again.", "danger")
        print("Error during event registration:", e)

    finally:
        # Close the database connection
        conn.close()

    # Redirect to the join event page
    return redirect(url_for('join_event'))


@app.route('/create_event', methods=['GET', 'POST'])
def create_event():
    if 'user_id' not in session or session['role'] != 'coordinator':
        return redirect(url_for('index'))

    if request.method == 'POST':
        event_name = request.form['event_name']
        event_type = request.form['event_type']
        venue = request.form['venue']
        timings = request.form['timings']
        date = request.form['date']
        max_students = int(request.form['max_students'])
        coordinator_id = session['user_id']

        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("INSERT INTO events (coordinator_id, event_name, event_type, venue, timings, date, max_students) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (coordinator_id, event_name, event_type, venue, timings, date, max_students))
        conn.commit()
        conn.close()

        flash("Event created successfully!", "success")
        return redirect(url_for('coordinator_dashboard'))
    return render_template('create_event.html')
@app.route('/coordinator_dashboard')
def coordinator_dashboard():
    if 'user_id' not in session or session['role'] != 'coordinator':
        return redirect(url_for('index'))

    conn = sqlite3.connect('users.db')
    c = conn.cursor()

    # Get current date for filtering events
    current_date = datetime.now().date()

    # Fetch all events created by the coordinator
    c.execute("SELECT * FROM events WHERE coordinator_id = ?", (session['user_id'],))
    created_events = c.fetchall()
    
    # Categorizing events
    scheduled_events, live_events, past_events = [], [], []
    
    for event in created_events:
        event_date = datetime.strptime(event[6], '%Y-%m-%d').date()
        event_data = {
            "id": event[0],
            "name": event[2],
            "event_type": event[3],
            "venue": event[4],
            "timings": event[5],
            "date": event[6],
            "max_students": event[7],
            "registration_count": event[8]
        }

        if event_date < current_date:
            past_events.append(event_data)
        elif event_date == current_date:
            live_events.append(event_data)
        else:
            scheduled_events.append(event_data)

    conn.close()

    return render_template('coordinator_dashboard.html', scheduled_events=scheduled_events, live_events=live_events, past_events=past_events)
@app.route('/view_event_registrations/<int:event_id>')
def view_event_registrations(event_id):
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect(url_for('index'))

    # Connect to the database
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Fetch registrations for the specified event
    c.execute("""
        SELECT users.name, users.uid 
        FROM event_registrations 
        JOIN users ON event_registrations.user_id = users.id 
        WHERE event_registrations.event_id = ?
    """, (event_id,))
    
    registrations = c.fetchall()
    conn.close()

    # Render the template and pass registrations and event_id
    return render_template('view_event_registrations.html', registrations=registrations, event_id=event_id)

@app.route('/download_registrations/<int:event_id>')
def download_registrations(event_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))

    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Fetch registrations for the specified event
    c.execute("""
        SELECT users.name, users.uid 
        FROM event_registrations 
        JOIN users ON event_registrations.user_id = users.id 
        WHERE event_registrations.event_id = ?
    """, (event_id,))
    registrations = c.fetchall()
    conn.close()

    # Create a DataFrame from the registrations
    df = pd.DataFrame(registrations, columns=['Name', 'User ID'])

    # Create a BytesIO object to save the Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Registrations')

    # Move the cursor to the beginning of the stream
    output.seek(0)

    # Send the Excel file as a response
    return send_file(output, as_attachment=True, download_name='event_registrations.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
