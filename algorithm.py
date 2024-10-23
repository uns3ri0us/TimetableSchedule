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

    # Verify the course-to-department mapping
    course_department_map = {course['course_name']: course['department'] for course in courses_data}

    return courses_data, lecturer_data, room_data, department_id_map, course_department_map

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

    # Initialize course counts for each day and department
    course_counts_per_day = [{department: {} for department in {course['department'] for course in courses_data}} for _ in range(5)]
    course_counts = {course['course_name']: 0 for course in courses_data}

    for slot_idx, course_idx in enumerate(solution):
        if course_idx == -1:
            continue

        course_idx = int(course_idx)
        course = courses_data[course_idx]
        lecturer_name = course['lecturer']
        student_count = course['student_count']
        department_id = course['department']
        assigned_room = room_data[slot_idx % len(room_data)]
        day_index = (slot_idx // 9) % 5  # Calculate the day index

        # Room capacity check
        if student_count > assigned_room['capacity']:
            penalty += 10

        # Lecturer availability check
        if slot_idx not in lecturer_availability.get(lecturer_name, []):
            penalty += 10

        # Double booking check
        if lecturer_schedule[lecturer_name][slot_idx] != -1:
            penalty += 15
        else:
            lecturer_schedule[lecturer_name][slot_idx] = course_idx

        # Room conflict check
        if room_usage[slot_idx] != -1:
            penalty += 10
        else:
            room_usage[slot_idx] = course_idx

        # Check for consecutive session logic
        if course['credit_hours'] == 2:
            next_slot = slot_idx + 1
            if next_slot < len(solution):
                next_course_idx = solution[next_slot]
                next_room = room_data[next_slot % len(room_data)]
                if next_course_idx != course_idx or next_room != assigned_room:
                    penalty += 20

        # Track course counts per day and department
        if department_id not in course_counts_per_day[day_index]:
            course_counts_per_day[day_index][department_id] = {}

        if course['course_name'] not in course_counts_per_day[day_index][department_id]:
            course_counts_per_day[day_index][department_id][course['course_name']] = 0

        course_counts_per_day[day_index][department_id][course['course_name']] += 1

        # Check if daily course limit is exceeded
        if course_counts_per_day[day_index][department_id][course['course_name']] > 1:
            penalty += 20

        # Check for three consecutive slots of the same course
        if (slot_idx > 1 and 
            solution[slot_idx] == solution[slot_idx - 1] == solution[slot_idx - 2]):
            penalty += 30

    # Validate total assigned hours against required hours
    for course in courses_data:
        assigned_hours = course_counts[course['course_name']]
        required_hours = course['credit_hours']
        if assigned_hours != required_hours:
            penalty += abs(assigned_hours - required_hours) * 10

    return 1 + penalty

def repair_solution(solution, courses_data, room_data, department_id_map):
    course_counts = {course_idx: 0 for course_idx in range(len(courses_data))}

    for slot_idx, course_idx in enumerate(solution):
        if course_idx != -1:
            course_counts[course_idx] += 1

    for course_idx, course in enumerate(courses_data):
        required_hours = course['credit_hours']
        assigned_hours = course_counts[course_idx]
        department = course['department']
        department_id = department_id_map[department]

        # Calculate the starting index for the department
        department_start_idx = department_id * 45

        # Ensure courses stay within their department’s slots
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
            for idx in range(department_start_idx, department_start_idx + 45):
                if solution[idx] == -1:
                    solution[idx] = course_idx
                    slots_to_add -= 1
                    if slots_to_add == 0:
                        break

    return solution

# Run the genetic algorithm
def run_genetic_algorithm():
    courses_data, lecturer_data, room_data, department_id_map, _ = fetch_data()
    num_departments = len(department_id_map)
    num_time_slots = 45  # 9 slots * 5 days

    lecturer_availability = {lecturer['username']: get_lecturer_availability(lecturer) for lecturer in lecturer_data}
    gene_space = [-1] + list(range(len(courses_data)))

    def fitness_wrapper(ga_instance, solution, solution_idx):
        return fitness_func(ga_instance, solution, solution_idx, lecturer_availability, room_data, courses_data, lecturer_data, num_departments)

    def on_generation(ga_instance):
        for idx, solution in enumerate(ga_instance.population):
            ga_instance.population[idx] = repair_solution(solution.copy(), courses_data, room_data, department_id_map)

    ga = pygad.GA(
        num_generations=5000,
        sol_per_pop=100,
        num_parents_mating=30,
        fitness_func=fitness_wrapper,
        num_genes=num_departments * num_time_slots,
        gene_space=gene_space,
        parent_selection_type="tournament",
        crossover_type="single_point",
        mutation_probability=0.1,
        crossover_probability=0.9,
        on_generation=on_generation,
        keep_parents=10
    )
    ga.run()
    solution, fitness, _ = ga.best_solution()
    return solution, fitness

# Save timetable to the database
def save_timetable_to_db(solution, courses_data, room_data, lecturer_data):
    timetable = []
    lecturer_mapping = {lecturer['username']: lecturer['username'] for lecturer in lecturer_data}
    _, _, _, department_id_map, course_department_map = fetch_data()

    for department, department_id in department_id_map.items():
        department_start_idx = department_id * 45

        for slot_idx in range(department_start_idx, department_start_idx + 45):
            course_idx = solution[slot_idx]
            if course_idx == -1:
                continue
            
            course_idx = int(course_idx)
            course_info = courses_data[course_idx]
            course_department = course_info['department']

            # Verify department consistency
            if course_department != department:
                print(f"Warning: Course {course_info['course_name']} in wrong department ({course_department} vs {department})")
                continue  # Skip incorrect assignments

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

