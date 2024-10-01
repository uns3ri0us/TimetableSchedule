from flask import Flask, render_template, request, redirect, url_for, flash
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey"

# MongoDB configuration
app.config["MONGO_URI"] = "mongodb://localhost:27017/college_timetable"
mongo = PyMongo(app)

# Collection for storing users
users_collection = mongo.db.users

# Route to the registration page
@app.route('/', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get form data
        username = request.form.get('username')
        email = request.form.get('email')
        role = request.form.get('role')
        password = request.form.get('password')
        department = request.form.get('department')

        # Availability only for lecturers
        availability = {
            'monday': request.form.getlist('monday'),
            'tuesday': request.form.getlist('tuesday'),
            'wednesday': request.form.getlist('wednesday'),
            'thursday': request.form.getlist('thursday'),
            'friday': request.form.getlist('friday')
        } if role == 'lecturer' else None

        # Hash the password
        hashed_password = generate_password_hash(password)

        # Insert user data into MongoDB
        users_collection.insert_one({
            'username': username,
            'email': email,
            'role': role,
            'password': hashed_password,
            'department': department,
            'availability': availability
        })

        flash(f'User {username} registered successfully!')
        return redirect(url_for('register'))  # Redirect to the same page after registration

    return render_template('register.html')  # Render the registration form

if __name__ == '__main__':
    app.run(debug=True)
