from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Configuring MongoDB
app.config["MONGO_URI"] = "mongodb://localhost:27017/college_timetable"
mongo = PyMongo(app)

# Collections for different entities
rooms_collection = mongo.db.rooms
courses_collection = mongo.db.courses
users_collection = mongo.db.users

# Ensure user is logged in and has the right role before accessing certain routes
@app.before_request
def check_if_logged_in():
    restricted_endpoints = ['admin_dashboard', 'lecturer_dashboard', 'room_page', 'course_page', 'lecturer_page']
    if request.endpoint in restricted_endpoints:
        if 'user_id' not in session:
            flash('Please log in to access this page.')
            return redirect(url_for('login'))
        
        # Restrict access to certain pages based on user role
        if request.endpoint == 'admin_dashboard' and session.get('role') != 'admin':
            flash('Access denied. Admins only.')
            return redirect(url_for('login'))
        
        if request.endpoint == 'lecturer_dashboard' and session.get('role') != 'lecturer':
            flash('Access denied. Lecturers only.')
            return redirect(url_for('login'))

# Route to login page
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Find user in MongoDB
        user = users_collection.find_one({'username': username})

        if user and check_password_hash(user['password'], password):
            # Set session data
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            session['role'] = user['role']

            # Redirect based on role
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user['role'] == 'lecturer':
                return redirect(url_for('lecturer_dashboard'))
        else:
            flash('Invalid credentials. Please try again.')

    return render_template('login.html')

# Route to admin dashboard (Admin only)
@app.route('/admin')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    return render_template('admin_dashboard.html')

# Route to lecturer dashboard (Lecturer only)
@app.route('/lecturer')
def lecturer_dashboard():
    if session.get('role') != 'lecturer':
        return redirect(url_for('login'))
    return render_template('lecturer_dashboard.html')

# Route to logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Room management page (Admin only)
@app.route('/rooms')
def room_page():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    rooms = rooms_collection.find()
    return render_template('rooms.html', rooms=rooms)

# Route to add a new room (Admin only)
@app.route('/add_room', methods=['POST'])
def add_room():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    room_name = request.form.get('room_name')
    capacity = request.form.get('capacity')
    room_type = request.form.get('room_type')

    if room_name and capacity and room_type:
        rooms_collection.insert_one({
           'room_name': room_name,
           'capacity': int(capacity),
           'room_type': room_type,
        })
        flash('Room added successfully!')
    else:
        flash('All fields are required!')
    
    return redirect(url_for('room_page'))

# Course management page (Admin only)
@app.route('/courses')
def course_page():
    if session.get('role') not in ['admin']:
        return redirect(url_for('login'))
    
    courses = courses_collection.find()
    lecturers = users_collection.find({'role': 'lecturer'})
    return render_template('courses.html', courses=courses, lecturers=lecturers)

# Route to add a new course (Admin only)
@app.route('/add_course', methods=['POST'])
def add_course():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    course_code = request.form.get('course_code')
    course_name = request.form.get('course_name')
    lecturer = request.form.get('lecturer')
    credit_hours = request.form.get('credit_hours')
    lab_hours = request.form.get('lab_hours')

    if course_code and course_name and lecturer and credit_hours:
        courses_collection.insert_one({
            'course_code': course_code,
            'course_name': course_name,
            'lecturer': lecturer,
            'credit_hours': int(credit_hours),
            'lab_hours': int(lab_hours) if lab_hours else 0
        })
        flash('Course added successfully!')
    else:
        flash('All fields are required except for lab hours!')

    return redirect(url_for('course_page'))

# Lecturer management page (Admin only)
@app.route('/lecturers')
def lecturer_page():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    lecturers = users_collection.find({'role': 'lecturer'})
    return render_template('lecturers.html', lecturers=lecturers)

if __name__ == '__main__':
    app.run(debug=True)
