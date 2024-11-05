from database import courses_collection, users_collection, rooms_collection, timetable_collection
import random
import copy

# Constants
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
HOURS = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17]  # 8 AM - 6 PM
LUNCH_HOURS = [12, 13]  # 12-13 or 13-14 for lunch break
MAX_CONSECUTIVE_HOURS = 5
MAX_GENERATIONS = 100
POPULATION_SIZE = 50
MUTATION_RATE = 0.1

def get_courses():
    return list(courses_collection.find())

def get_users():
    return list(users_collection.find({"role": "lecturer"}))

def get_rooms():
    return list(rooms_collection.find())

def lecturer_availability(lecturer):
    lecturer = users_collection.find_one({"username": lecturer})
    return lecturer["availability"]  # List of available time slots

def room_capacity_check(room, course):
    return room["capacity"] >= course["student_count"]

def is_lab_required(course):
    # We can assume that a course is lab-based if lab_hours is greater than 0
    return course["lab_hours"] > 0

def generate_random_timetable(courses, rooms, lecturers):
    timetable = []
    for course in courses:
        lecturer_id = course["lecturer"]
        lab_hours = course["lab_hours"]
        credit_hours = course["credit_hours"] - lab_hours  # Subtract lab hours from credit hours
        
        # Lecture room assignment
        if credit_hours > 0:
            valid_rooms = [r for r in rooms if (is_lab_required(course) == (r["room_type"] != "lab") and room_capacity_check(r, course))]
            print(f"Valid rooms for course '{course['course_name']}' (Credit Hours): {valid_rooms}")  # Debugging output
            
            if not valid_rooms:
                print(f"No valid rooms found for course '{course['course_name']}'")  # Warning
                continue  # Skip to the next course

            room = random.choice(valid_rooms)
            day = random.choice(DAYS)
            start_hour = random.choice([h for h in HOURS if h <= 15 - credit_hours])  # Ensure enough space for lecture hours

            timetable.append({
                "course": course,  # Store the entire course object
                "lecturer": lecturer_id,
                "room": room["room_name"],
                "day": day,
                "start_hour": start_hour,
                "end_hour": start_hour + credit_hours,
                "department": course["department"]
            })

        # Lab room assignment
        if lab_hours > 0:
            valid_lab_rooms = [r for r in rooms if r["room_type"] == "lab" and room_capacity_check(r, course)]
            print(f"Valid lab rooms for course '{course['course_name']}': {valid_lab_rooms}")  # Debugging output
            
            if not valid_lab_rooms:
                print(f"No valid lab rooms found for course '{course['course_name']}'")  # Warning
                continue  # Skip to the next course
            
            lab_room = random.choice(valid_lab_rooms)
            day = random.choice(DAYS)
            start_hour = random.choice([h for h in HOURS if h <= 15 - lab_hours])  # Ensure enough space for lab hours
            
            timetable.append({
                "course": course,  # Store the entire course object for lab
                "lecturer": lecturer_id,
                "room": lab_room["room_name"],
                "day": day,
                "start_hour": start_hour,
                "end_hour": start_hour + lab_hours,
                "department": course["department"]
            })

    return timetable

def fitness(timetable):
    score = 0

    for entry in timetable:
        if entry["end_hour"] - entry["start_hour"] != (entry["course"]["credit_hours"] + entry["course"]["lab_hours"]):
            score -= 5  # Penalize if total hours do not match

    # Rule 1: Lecturer availability check
    for entry in timetable:
        lecturer_slots = lecturer_availability(entry["lecturer"])
        if (entry["day"], entry["start_hour"]) in lecturer_slots:
            score += 1

    # Rule 2: No department clashes
    rooms_per_slot = {}
    for entry in timetable:
        key = (entry["day"], entry["start_hour"], entry["room"])
        if key not in rooms_per_slot:
            rooms_per_slot[key] = []
        rooms_per_slot[key].append(entry["course"])

    for slot, courses in rooms_per_slot.items():
        if len(courses) > 1:
            score -= len(courses)  # Penalize clashes

    # Rule 3: No more than 5 consecutive hours for any lecturer
    lecturer_hours = {}
    for entry in timetable:
        if entry["lecturer"] not in lecturer_hours:
            lecturer_hours[entry["lecturer"]] = []
        lecturer_hours[entry["lecturer"]].append(entry["start_hour"])

    for hours in lecturer_hours.values():
        hours.sort()
        if any(hours[i + 4] - hours[i] <= 4 for i in range(len(hours) - 4)):
            score -= 5  # Penalize overwork

    # Rule 4: Ensure consecutive hours for multi-hour classes
    for entry in timetable:
        if entry["end_hour"] - entry["start_hour"] != (entry["course"]["credit_hours"] + entry["course"]["lab_hours"]):
            score -= 2  # Penalize split hours

    # Rule 5: At least one lunch hour reserved
    lunch_breaks = sum(1 for entry in timetable if entry["start_hour"] in LUNCH_HOURS)
    if lunch_breaks == 0:
        score -= 10  # Penalize missing lunch break

    print(score)
    return score

def selection(population):
    population.sort(key=lambda x: fitness(x), reverse=True)
    return population[:10]  # Select top 10

def crossover(parent1, parent2):
    point = random.randint(0, len(parent1) - 1)
    child = parent1[:point] + parent2[point:]
    return child

def mutate(timetable):
    if random.random() < MUTATION_RATE:
        course = random.choice(timetable)
        course["day"] = random.choice(DAYS)
        course["start_hour"] = random.choice(HOURS)
    return timetable

def genetic_algorithm():
    courses = get_courses()
    rooms = get_rooms()
    lecturers = get_users()

    # Initialize a random population
    population = [generate_random_timetable(courses, rooms, lecturers) for _ in range(POPULATION_SIZE)]

    # Evolve for a fixed number of generations
    for generation in range(MAX_GENERATIONS):
        population = selection(population)  # Select top performers
        new_population = []

        while len(new_population) < POPULATION_SIZE:
            parent1, parent2 = random.sample(population, 2)
            child = crossover(parent1, parent2)
            child = mutate(child)
            new_population.append(child)

        population = new_population  # Update population

    # Get the best timetable from the final population
    best_timetable = max(population, key=lambda x: fitness(x))
    return best_timetable

def store_timetable(timetable):
    # First, clear the old entries (optional, to avoid duplicate schedules)
    timetable_collection.delete_many({})

    # Insert new timetable entries
    formatted_entries = []
    for entry in timetable:
        formatted_entries.append({
            "course": entry["course"],
            "lecturer": entry["lecturer"],
            "room": entry["room"],
            "day": entry["day"],
            "start_hour": entry["start_hour"],
            "end_hour": entry["end_hour"],
            "department": entry["department"]
        })

    timetable_collection.insert_many(formatted_entries)
    print(f"Stored {len(formatted_entries)} timetable entries successfully.")
