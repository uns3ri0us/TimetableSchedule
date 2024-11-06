from flask import jsonify, request, session, render_template, redirect, flash
import json
import datetime
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from algorithm import run_genetic_algorithm, save_timetable_to_db  # Import the separated algorithm
from bson.objectid import ObjectId  # Ensure you import ObjectId

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Subject to change

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
    # Define all endpoints that are restricted to certain users
    admin_endpoints = [
        'generate_timetable', 'room_page', 'add_room', 'course_list',
        'add_course', 'lecturer_page', 'admin_requests', 'accept_request',
        'reject_request', 'room_stats', 'timetable_view', 'admin_dashboard'
    ]
    lecturer_endpoints = [
        'lecturer_dashboard', 'lecturer_courses', 'lecturer_timetable', 
        'request_replacement', 'check_availability'
    ]
    student_endpoints = [
        'student_dashboard'
    ]
    
    # Ensure user is logged in for restricted pages
    if request.endpoint in admin_endpoints + lecturer_endpoints:
        if 'user_id' not in session:
            flash('Please log in to access this page.')
            return redirect(url_for('login'))
        
        # Restrict access to certain pages based on user role
        if request.endpoint in admin_endpoints and session.get('role') != 'admin':
            flash('Access denied. Admins only.')
            return redirect(url_for('login'))
        
        if request.endpoint in lecturer_endpoints and session.get('role') != 'lecturer':
            flash('Access denied. Lecturers only.')
            return redirect(url_for('login'))
        
        if request.endpoint in student_endpoints and session.get('role') != 'student':
            flash('Access denied. Students only.')
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
            if user['role'] == 'student':
                session['student_name'] = user['username']
                session['department'] = user['department']

            # Redirect based on role
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user['role'] == 'lecturer':
                return redirect(url_for('lecturer_dashboard'))
            elif user['role'] == 'student':
                return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid credentials. Please try again.')

    return render_template('login.html')

# Route to admin dashboard (Admin only)
@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    return render_template('admin_dashboard.html')

# Route to lecturer dashboard (Lecturer only)
@app.route('/lecturer')
def lecturer_dashboard():
    if 'user_id' not in session or session.get('role') != 'lecturer':
        return redirect(url_for('login'))
    return render_template('lecturer_dashboard.html')

# Route to student dashboard (Student only)
@app.route('/student')
def student_dashboard():
    if 'user_id' not in session or session.get('role') != 'student':
        return redirect(url_for('login'))
    
    student_name = session.get('username')
    department = session.get('department')  # Get student's department from session
    timetable = list(timetable_collection.find({"department": department}))  # Fetch timetable for the lecturer

    # Print for debugging
    print("Timetable Data:", timetable)
    return render_template('student_dashboard.html', timetable=timetable)

# Route to logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/admintimetable', methods=['GET', 'POST'])
def generate_timetable():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
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
        timetable_solution, fitness = run_genetic_algorithm()

        # Generate the detailed timetable for display and saving
        detailed_timetable = save_timetable_to_db(timetable_solution, selected_courses, room_data, lecturer_data)

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
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    rooms = rooms_collection.find()
    return render_template('rooms.html', rooms=rooms)

# Route to add a new room (Admin only)
@app.route('/add_room', methods=['POST'])
def add_room():
    if 'user_id' not in session or session.get('role') != 'admin':
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
def course_list():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    # Fetch all courses from the collection
    courses = list(courses_collection.find())

    # Fetch distinct departments from the lecturer collection
    departments = users_collection.distinct('department')

    # Fetch all lecturers with their departments
    lecturers = list(users_collection.find({}, {'username': 1, 'department': 1, '_id': 0}))

    return render_template(
        'courses.html', 
        courses=courses, 
        departments=departments, 
        lecturers=lecturers
    )


# Route to add a new course (Admin only)
@app.route('/add_course', methods=['POST'])
def add_course():
    if 'user_id' not in session or session.get('role') != 'admin':
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
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    lecturers = users_collection.find({'role': 'lecturer'})
    return render_template('lecturers.html', lecturers=lecturers)

@app.route('/request')
def admin_requests():
    # Ensure the user is logged in and is an admin
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))

    # Retrieve all requests from the database
    requests = list(request_collection.find({'status' : 'pending'}))  # This will return an empty list if there are no requests

    return render_template('request.html', requests=requests)

@app.route('/admin/accept_request/<request_id>', methods=['POST'])
def accept_request(request_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403

    # Retrieve the request
    request = request_collection.find_one({"_id": ObjectId(request_id)})
    if not request:
        return jsonify({"error": "Request not found"}), 404

    # Extract the requested slot and details
    slot_details = request.get("timeslots")  # Example format: 'Wednesday 13:00 - 14:00'
    slot_id = request.get("slot_id")
    replacement_type = request.get("replacement_type")

    if replacement_type == "permanent":
        # Split slot_details into day and time components
        if slot_details:
            day, time_range = slot_details.split(' ', 1)  # Splits into day and time

            # Update the timetable with the separated details
            timetable_collection.update_one(
                {"_id": ObjectId(slot_id)},
                {"$set": {
                    "day": day,
                    "time": time_range,
                }}
            )

        # Update the request's status to accepted
        request_collection.update_one(
            {"_id": ObjectId(request_id)},
            {"$set": {"status": "Accepted"}}
        )
    else:
        # Update the request's status to accepted
        request_collection.update_one(
            {"_id": ObjectId(request_id)},
            {"$set": {"status": "Accepted"}}
        )


    return jsonify({"message": "Request accepted successfully!"}), 200

@app.route('/admin/reject_request/<request_id>', methods=['POST'])
def reject_request(request_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized"}), 403

    reject_reason = request.form.get("rejectReason")
    
    # Update the request's status to rejected and add rejection reason
    request_collection.update_one(
        {"_id": ObjectId(request_id)},
        {"$set": {
            "status": "Rejected",
            "rejection_reason": reject_reason
        }}
    )

    return jsonify({"message": "Request rejected successfully!"}), 200


@app.route('/roomstats')
def room_stats():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))

    # Fetch all timetable entries
    timetable_entries = list(timetable_collection.find())

    # Initialize a dictionary to hold room usage stats
    room_usage = {}

    # Count bookings per room
    for entry in timetable_entries:
        room = entry.get('room')  # Safely get room name
        if room:  # Check if room is not None or empty
            if room not in room_usage:
                room_usage[room] = 0
            room_usage[room] += 1  # Increment the booking count for the room

    # Prepare data for rendering
    stats = []
    total_slots = 45  # Maximum possible slots per week
    for room, count in room_usage.items():
        usage_percentage = (count / total_slots) * 100  # Calculate usage percentage
        stats.append({
            'room': room,
            'count': count,
            'usage_percentage': usage_percentage
        })

    return render_template('roomstats.html', stats=stats)

@app.route('/timetable_view')
def timetable_view():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))

    # Fetch all lecturers, rooms, and departments from the database
    lecturers = users_collection.find({'role':'lecturer'}, {'username': 1, '_id': 0})
    rooms = timetable_collection.distinct('room')
    departments = timetable_collection.distinct('department')

    return render_template(
        'timetableview.html',
        lecturers=list(lecturers),
        rooms=rooms,
        departments=departments
    )


# Helper route to fetch timetable data dynamically
@app.route('/get_timetable/<entity_type>/<entity_name>')
def get_timetable(entity_type, entity_name):

    query = {}
    if entity_type == 'lecturer':
        query = {'lecturer': entity_name}
    elif entity_type == 'room':
        query = {'room': entity_name}
    elif entity_type == 'department':
        query = {'department': entity_name}

    # Find all relevant timetable entries
    timetable_entries = timetable_collection.find(query)
    
    # Prepare data for JSON response
    timetable_data = [
        {
            'day': entry['day'],
            'time': entry['time'],
            'course': entry['course'],
            'room': entry['room']
        }
        for entry in timetable_entries
    ]
    
    return jsonify(timetable_data)

############################################################# LECTURER SIDE ####################################

@app.route('/lecturertimetable', methods=['GET'])
def lecturer_timetable():
    if 'user_id' not in session or session.get('role') != 'lecturer':
        return redirect(url_for('login'))
    
    lecturer_name = session.get('lecturer_name')  # Get lecturer's name from session
    timetable = list(timetable_collection.find({"lecturer": lecturer_name}))  # Fetch timetable for the lecturer

    # Print for debugging
    print("Timetable Data:", timetable)

    return render_template("lecturer_timetable.html", timetable=timetable)

def generate_time_slots():
    """Generate hourly time slots from 08:00 to 18:00."""
    slots = []
    start = datetime.strptime("08:00", "%H:%M")
    end = datetime.strptime("18:00", "%H:%M")

    while start < end:
        next_slot = start + timedelta(hours=1)
        slots.append(f"{start.strftime('%H:%M')} - {next_slot.strftime('%H:%M')}")
        start = next_slot
    return slots

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


@app.route('/check_availability')
def check_availability():
    if 'user_id' not in session or session.get('role') != 'lecturer':
        return redirect(url_for('login'))

    venue = request.args.get('venue')

    # Fetch all timetable entries for the selected venue
    booked_slots = timetable_collection.find({"room": venue})
    
    if not booked_slots:
        print(f"No bookings found for room: {venue}")

    # Initialize availability dictionary
    availability = {day: [] for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]}

    # Populate the availability dictionary
    for slot in booked_slots:
        day = slot['day']
        time = slot['time']
        availability[day].append(time)

    return jsonify(availability)

@app.route('/lecturerrequest', methods=['GET', 'POST'])
def request_replacement():
    if 'user_id' not in session or session.get('role') != 'lecturer':
        return redirect(url_for('login'))

    if request.method == 'POST':
        lecturer_name = session.get('lecturer_name')
        reason = request.form['reason']
        slot_id = request.form['replace_slot']
        slot_details = request.form['slot_details']
        replacement_type = request.form['replacementType']
        specific_date = request.form.get('specificDate') if replacement_type == 'temporary' else None
        venue = request.form['venue']
        timeslots = request.form.get('timeslot')

        # Store the request data in the database
        request_data = {
            'lecturer_name': lecturer_name,
            'reason': reason,
            'slot_id': slot_id,
            'slot_details': slot_details,
            'replacement_type': replacement_type,
            'specific_date': specific_date,
            'venue': venue,
            'timeslots': timeslots,
            'status': 'pending',
            'submitted_at': datetime.now()
        }
        mongo.db.requests.insert_one(request_data)

        flash('Replacement request submitted successfully!', 'success')
        return redirect('/lecturer')

    rooms = list(mongo.db.rooms.find())  # Fetch available rooms

    lecturer = session.get('lecturer_name')
    slots = timetable_collection.find({"lecturer": lecturer})  # Fetch slots to replace
    
    return render_template('lecturer_request.html', rooms=rooms, slots=slots)

if __name__ == '__main__':
    app.run(debug=True)
