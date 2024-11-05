import pygad
import numpy as np
from pymongo import MongoClient
from database import (
    courses_collection, users_collection, rooms_collection, timetable_collection
)

# Fetch courses, lecturers, and rooms data from the database
def fetch_data():
    courses_data = list(courses_collection.find())
    lecturer_data = list(users_collection.find({'role': 'lecturer'}))
    room_data = list(rooms_collection.find())
    return courses_data, lecturer_data, room_data

# Lecturer availability
def get_lecturer_availability(lecturer):
    availability = lecturer.get('availability', {})
    available_slots = []
    days_mapping = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4}

    for day, times in availability.items():
        if day in days_mapping:
            day_index = days_mapping[day]
            for time_range in (times if isinstance(times, list) else [times]):
                start, end = map(lambda t: int(t.split(":")[0]), time_range.split("-"))
                available_slots.extend([(day_index * 9) + hour - 8 for hour in range(start, end)])
    return available_slots

# Enhanced fitness function
def fitness_func(ga_instance, solution, solution_idx, lecturer_availability, room_data, courses_data, lecturer_data):
    penalty = 0
    lecturer_schedule = {lecturer['username']: [-1] * 45 for lecturer in lecturer_data}
    room_usage = [-1] * 45
    course_counts_per_day = [{} for _ in range(5)]  # Track counts for each day
    course_counts = {course['course_name']: 0 for course in courses_data}

    for slot_idx, course_idx in enumerate(solution):
        if course_idx == -1:
            continue

        course_idx = int(course_idx)
        course = courses_data[course_idx]
        lecturer_name = course['lecturer']
        student_count = course['student_count']
        assigned_room = room_data[slot_idx % len(room_data)]
        day_index = slot_idx // 9  # Calculate the day index

        # Room capacity check
        if student_count > assigned_room['capacity']:
            penalty += 10  # Penalize room overflow

        # Lecturer availability check
        if slot_idx not in lecturer_availability.get(lecturer_name, []):
            penalty += 10  # Penalize unavailable slots

        # Double booking check for the same lecturer
        if lecturer_schedule[lecturer_name][slot_idx] != -1:
            penalty += 15  # Strong penalty for double booking
        else:
            lecturer_schedule[lecturer_name][slot_idx] = course_idx

        # Room conflict check
        if room_usage[slot_idx] != -1:
            penalty += 10  # Penalize room conflicts
        else:
            room_usage[slot_idx] = course_idx

        # Ensure 2-hour sessions are in the same room
        if course['credit_hours'] == 2:
            next_slot = slot_idx + 1
            if next_slot < len(solution):
                next_course_idx = solution[next_slot]
                next_room = room_data[next_slot % len(room_data)]

                # Penalize if the next slot isn't the same course
                if next_course_idx != course_idx:
                    penalty += 20  # Penalize if not the same course

                # Penalize if not in the same room
                if next_room != assigned_room:
                    penalty += 20  # Penalize if not in the same room

        # Track course assignments for credit hour validation and daily limit
        course_counts[course['course_name']] += 1

        # Count course hours for the day
        if course['course_name'] not in course_counts_per_day[day_index]:
            course_counts_per_day[day_index][course['course_name']] = 0
        course_counts_per_day[day_index][course['course_name']] += 1

        # Check if we exceed 2 hours in the same day
        if course_counts_per_day[day_index][course['course_name']] > 1:
            penalty += 20  # Penalize for exceeding daily limit for the same course

        # Check for three consecutive slots of the same course
        if (slot_idx > 0 and 
            solution[slot_idx - 1] == course_idx and 
            (slot_idx > 1 and solution[slot_idx - 2] == course_idx)):
            penalty += 30  # Penalize for three consecutive hours of the same course

    # Validate total assigned hours against required hours
    for course in courses_data:
        assigned_hours = course_counts[course['course_name']]
        required_hours = course['credit_hours']
        if assigned_hours != required_hours:
            penalty += abs(assigned_hours - required_hours) * 10  # Penalize hour mismatches

    return 1 / (1 + penalty)  # Higher fitness for fewer penalties

# Improved repair function
def repair_solution(solution, courses_data, room_data):
    course_counts = {}
    for slot_idx, course_idx in enumerate(solution):
        if course_idx != -1:
            course_counts[course_idx] = course_counts.get(course_idx, 0) + 1

    for course_idx, course in enumerate(courses_data):
        required_hours = course['credit_hours']
        assigned_hours = course_counts.get(course_idx, 0)

        # Remove excess slots
        if assigned_hours > required_hours:
            slots_to_remove = assigned_hours - required_hours
            for idx in range(len(solution)):
                if solution[idx] == course_idx:
                    solution[idx] = -1
                    slots_to_remove -= 1
                    if slots_to_remove == 0:
                        break

        # Add missing slots ensuring conditions for 2-hour sessions
        elif assigned_hours < required_hours:
            slots_to_add = required_hours - assigned_hours
            for idx in range(len(solution) - 1):
                if (
                    slots_to_add >= 2
                    and solution[idx] == -1
                    and solution[idx + 1] == -1
                    and room_data[idx % len(room_data)] == room_data[(idx + 1) % len(room_data)]
                ):
                    solution[idx] = course_idx
                    solution[idx + 1] = course_idx
                    slots_to_add -= 2
                elif slots_to_add > 0 and solution[idx] == -1:
                    solution[idx] = course_idx
                    slots_to_add -= 1

    return solution

# Run the genetic algorithm
def run_genetic_algorithm():
    courses_data, lecturer_data, room_data = fetch_data()
    num_time_slots = 45  # 9 time slots * 5 days

    lecturer_availability = {lecturer['username']: get_lecturer_availability(lecturer) for lecturer in lecturer_data}
    gene_space = [-1] + [i for i in range(len(courses_data))]

    def fitness_wrapper(ga_instance, solution, solution_idx):
        return fitness_func(ga_instance, solution, solution_idx, lecturer_availability, room_data, courses_data, lecturer_data)

    def on_generation(ga_instance):
        print(f"Generation {ga_instance.generations_completed}: Best Fitness = {ga_instance.best_solution()[1]}")

        for idx, solution in enumerate(ga_instance.population):
            ga_instance.population[idx] = repair_solution(solution.copy(), courses_data, room_data)

    ga = pygad.GA(
        num_generations=10000,
        sol_per_pop=200,
        num_parents_mating=50,
        fitness_func=fitness_wrapper,
        num_genes=num_time_slots,
        gene_space=gene_space,
        parent_selection_type="tournament",
        crossover_type="single_point",
        mutation_probability=0.2,
        crossover_probability=0.8,
        on_generation=on_generation,
        keep_parents=10  # Elitism: retain top 10 parents
    )
    ga.run()
    solution, fitness, _ = ga.best_solution()
    return solution, fitness

def save_timetable_to_db(solution, courses_data, room_data, lecturer_data):
    timetable = []

    # Update lecturer mapping to include department information
    lecturer_mapping = {
        lecturer['username']: {
            "name": lecturer['username'],
            "department": lecturer.get('department', 'Unknown Department')  # Default if department is missing
        } for lecturer in lecturer_data
    }

    for slot_idx, course_idx in enumerate(solution):
        if course_idx == -1:
            continue

        course_idx = int(course_idx)
        course_info = courses_data[course_idx]
        
        # Get lecturer details, including department
        lecturer_username = course_info['lecturer']
        lecturer_details = lecturer_mapping.get(lecturer_username, {
            "name": f"Unknown-{lecturer_username}",
            "department": "Unknown Department"
        })

        lecturer_name = lecturer_details["name"]
        department = lecturer_details["department"]

        # Room and time slot information
        assigned_room = room_data[slot_idx % len(room_data)]
        room_name = assigned_room.get('room_name', f"Room-{slot_idx % len(room_data)}")

        day_index = slot_idx // 9
        day = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"][day_index]
        time_slot = f"{8 + (slot_idx % 9)}:00 - {9 + (slot_idx % 9)}:00"

        # Insert the timetable entry into the database with department included
        timetable_collection.insert_one({
            "course": course_info['course_name'],
            "lecturer": lecturer_name,
            "department": department,   # Added department field
            "room": room_name,
            "day": day,
            "time": time_slot
        })
