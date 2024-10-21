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
    
    # Extract departments and create department-to-ID mapping
    departments = list({course['department'] for course in courses_data})
    department_id_map = {dept: idx for idx, dept in enumerate(departments)}
    
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
def fitness_func(ga_instance, solution, solution_idx, lecturer_availability, room_data, courses_data, lecturer_data, num_departments):
    penalty = 0
    lecturer_schedule = {lecturer['username']: [-1] * (num_departments * 45) for lecturer in lecturer_data}
    room_usage = [-1] * (num_departments * 45)

    # Initialize course_counts_per_day to contain all departments
    course_counts_per_day = [{department: {} for department in {course['department'] for course in courses_data}} for _ in range(5)]
    course_counts = {course['course_name']: 0 for course in courses_data}

    for slot_idx, course_idx in enumerate(solution):
        if course_idx == -1:
            continue

        course_idx = int(course_idx)
        course = courses_data[course_idx]
        lecturer_name = course['lecturer']
        student_count = course['student_count']
        department_id = course['department']  # Changed this variable name for clarity
        assigned_room = room_data[slot_idx % len(room_data)]
        day_index = (slot_idx // 9) % 5  # Calculate the day index

        # Check if department exists in course_counts_per_day for the current day
        if department_id not in course_counts_per_day[day_index]:
            # Initialize if department doesn't exist
            course_counts_per_day[day_index][department_id] = {}

        # Room capacity check
        if student_count > assigned_room['capacity']:
            penalty += 10  # Penalize room overflow

        # Lecturer availability check
        if slot_idx not in lecturer_availability.get(lecturer_name, []):
            penalty += 10  # Penalize unavailable slots

        # Double booking check for the same lecturer across all departments
        if lecturer_schedule[lecturer_name][slot_idx] != -1:
            penalty += 15  # Strong penalty for double booking
        else:
            lecturer_schedule[lecturer_name][slot_idx] = course_idx

        # Room conflict check across all departments
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
        if course['course_name'] not in course_counts_per_day[day_index][department_id]:
            course_counts_per_day[day_index][department_id][course['course_name']] = 0
            
        course_counts_per_day[day_index][department_id][course['course_name']] += 1

        # Check if we exceed 2 hours in the same day for a course within a department
        if course_counts_per_day[day_index][department_id][course['course_name']] > 1:
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
def repair_solution(solution, courses_data, room_data, department_id_map):
    course_counts = {course_idx: 0 for course_idx in range(len(courses_data))}

    for slot_idx, course_idx in enumerate(solution):
        if course_idx != -1:
            course_counts[course_idx] += 1

    for course_idx, course in enumerate(courses_data):
        required_hours = course['credit_hours']
        assigned_hours = course_counts[course_idx]
        department = course['department']
        department_id = department_id_map[department]  # Use numeric ID

        department_start_idx = department_id * 45

        if assigned_hours > required_hours:
            slots_to_remove = assigned_hours - required_hours
            for idx in range(department_start_idx, department_start_idx + 45):
                if solution[idx] == course_idx:
                    solution[idx] = -1
                    slots_to_remove -= 1
                    if slots_to_remove == 0:
                        break

        elif assigned_hours < required_hours:
            slots_to_add = required_hours - assigned_hours
            for idx in range(department_start_idx, department_start_idx + 44):
                if (slots_to_add >= 2 and solution[idx] == -1 and 
                    solution[idx + 1] == -1 and 
                    room_data[idx % len(room_data)] == room_data[(idx + 1) % len(room_data)]):
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
    
    # Calculate number of unique departments
    unique_departments = set(course['department'] for course in courses_data)
    num_departments = len(unique_departments)  # This should be an integer

    num_time_slots = 45  # 9 time slots * 5 days
    lecturer_availability = {lecturer['username']: get_lecturer_availability(lecturer) for lecturer in lecturer_data}
    gene_space = [-1] + [i for i in range(len(courses_data))]

    def fitness_wrapper(ga_instance, solution, solution_idx):
        return fitness_func(ga_instance, solution, solution_idx, lecturer_availability, room_data, courses_data, lecturer_data, num_departments)

    def on_generation(ga_instance):
        for idx, solution in enumerate(ga_instance.population):
            ga_instance.population[idx] = repair_solution(solution.copy(), courses_data, room_data, num_departments)

    ga = pygad.GA(
        num_generations=20000,
        sol_per_pop=75,
        num_parents_mating=25,
        fitness_func=fitness_wrapper,
        num_genes=num_departments * num_time_slots,
        gene_space=gene_space,
        parent_selection_type="tournament",
        crossover_type="single_point",
        mutation_probability=0.15,
        crossover_probability=0.85,
        on_generation=on_generation,
        keep_parents=15  # Elitism: retain top 10 parents
    )
    ga.run()
    solution, fitness, _ = ga.best_solution()
    return solution, fitness


def save_timetable_to_db(solution, courses_data, room_data, lecturer_data):
    timetable = []
    lecturer_mapping = {lecturer['username']: lecturer['name'] for lecturer in lecturer_data}
    _, _, _, department_id_map = fetch_data()

    for department, department_id in department_id_map.items():
        department_start_idx = department_id * 45

        for slot_idx in range(department_start_idx, department_start_idx + 45):
            course_idx = solution[slot_idx]
            if course_idx == -1:
                continue

            course_info = courses_data[course_idx]
            lecturer_name = lecturer_mapping.get(course_info['lecturer'], "Unknown")
            room_name = room_data[slot_idx % len(room_data)].get('room_name', f"Room-{slot_idx}")

            day = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"][(slot_idx // 9) % 5]
            time_slot = f"{8 + (slot_idx % 9)}:00 - {9 + (slot_idx % 9)}:00"

            timetable_entry = {
                "department": department,
                "course": course_info['course_name'],
                "lecturer": lecturer_name,
                "room": room_name,
                "day": day,
                "time": time_slot
            }
            timetable_collection.insert_one(timetable_entry)
            timetable.append(timetable_entry)

    return timetable
