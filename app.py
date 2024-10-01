import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from algorithm import run_genetic_algorithm, generate_detailed_timetable # Import the separated algorithm
from bson.objectid import ObjectId  # Ensure you import ObjectId

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Configuring MongoDB
app.config["MONGO_URI"] = "mongodb://localhost:27017/college_timetable"
mongo = PyMongo(app)

# Collections for different entities
rooms_collection = mongo.db.rooms
courses_collection = mongo.db.courses
users_collection = mongo.db.users
request_collection = mongo.db.requests
timetable_collection = mongo.db.timetables

# Expose collections by making them importable
__all__ = ['courses_collection', 'users_collection', 'rooms_collection', 'timetable_collection']

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
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            session['role'] = user['role']

            # Store lecturer name in session if logged in user is a lecturer
            if user['role'] == 'lecturer':
                session['lecturer_name'] = user['username']

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

@app.route('/admintimetable', methods=['GET', 'POST'])
def generate_timetable():
    if request.method == 'POST':
        # Get the selected courses from the form
        selected_course_ids = request.form.getlist('courses[]')
        
        if not selected_course_ids:
            flash('Please select at least one course!', 'danger')
            return redirect(url_for('generate_timetable'))

        # Fetch selected courses from the database
        selected_courses = list(courses_collection.find({'_id': {'$in': [ObjectId(course_id) for course_id in selected_course_ids]}}))

        # Fetch lecturers and room data
        lecturer_data = list(users_collection.find({'role': 'lecturer'}))
        room_data = list(rooms_collection.find())

        # Run the genetic algorithm with the selected courses
        timetable_solution, fitness = run_genetic_algorithm(selected_courses, lecturer_data, room_data)

        # Generate the detailed timetable for display and saving
        detailed_timetable = generate_detailed_timetable(timetable_solution, selected_courses, room_data)

        # Save the generated timetable into the database
        timetable_collection.insert_one({
            'timetable': detailed_timetable,
            'fitness': fitness
        })

        flash('Timetable successfully generated and saved!', 'success')
        return redirect(url_for('generate_timetable'))

    # Fetch available courses from the database
    available_courses = list(courses_collection.find())

    return render_template('timetable_gen.html', available_courses=available_courses)

# Room management page (Admin only)
@app.route('/adminrooms')
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
@app.route('/courselist')
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
    student_count = request.form.get('student_count')
    department = request.form.get('department')

    if course_code and course_name and lecturer and credit_hours:
        courses_collection.insert_one({
            'course_code': course_code,
            'course_name': course_name,
            'lecturer': lecturer,
            'credit_hours': int(credit_hours),
            'lab_hours': int(lab_hours) if lab_hours else 0,
            'student_count': int(student_count),
            'department': department
        })
        flash('Course added successfully!')
    else:
        flash('All fields are required except for lab hours!')

    return redirect(url_for('course_page'))

# Lecturer management page (Admin only)
@app.route('/lecturerlist')
def lecturer_page():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    lecturers = users_collection.find({'role': 'lecturer'})
    return render_template('lecturers.html', lecturers=lecturers)

@app.route('/lecturercourse')
def lecturer_courses():
    # Ensure the user is logged in and is a lecturer
    if 'user_id' not in session or session.get('role') != 'lecturer':
        return redirect(url_for('login'))
    
    # Find the current lecturer's username (or ID)
    lecturer_username = session.get('username')  # Assuming username is used to assign courses
    
    # Fetch courses assigned to the logged-in lecturer
    courses = list(courses_collection.find({'lecturer': lecturer_username}))  # Convert cursor to list

    return render_template('lecturer_course.html', courses=courses)

@app.route('/request')
def admin_requests():
# Ensure the user is logged in and is a lecturer
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))

    # Retrieve all requests from the database
    requests = list(request_collection.find())  # This will return an empty list if there are no requests
    
    return render_template('request.html', requests=requests)


@app.route('/lecturertimetable')
def lecturer_timetable():
    # Ensure the user is logged in and is a lecturer
    if 'user_id' not in session or session.get('role') != 'lecturer':
        return redirect(url_for('login'))
    
    return render_template('lecturer_timetable.html')

@app.route('/lecturerrequest', methods=['GET', 'POST'])
def request_replacement():
    if request.method == 'POST':
        lecturer_name = session.get('lecturer_name')
        reason = request.form['reason']
        replacement_type = request.form['replacementType']
        specific_date = request.form.get('specificDate') if replacement_type == 'temporary' else None
        venue = request.form['venue']
        timeslot = request.form['timeslot']

        # Create the request data to store in the database
        request_data = {
            'lecturer_name': lecturer_name,
            'reason': reason,
            'replacement_type': replacement_type,
            'specific_date': specific_date,
            'venue': venue,
            'timeslot': timeslot,
            'status': 'pending',
            'submitted_at': datetime.datetime.now()
        }

        # Insert the data into the requests collection
        mongo.db.requests.insert_one(request_data)

        flash('Replacement request submitted successfully!', 'success')
        return redirect('/lecturer')

    return render_template('lecturer_request.html')

if __name__ == '__main__':
    app.run(debug=True)