import pygad
import numpy as np
from pymongo import MongoClient
from database import (
    courses_collection, users_collection, rooms_collection, timetable_collection
)

# Fetch courses, lecturers, rooms, and existing timetable data from the database
def fetch_data():
    courses_data = list(courses_collection.find())
    lecturer_data = list(users_collection.find({'role': 'lecturer'}))
    room_data = list(rooms_collection.find())
    timetable_data = list(timetable_collection.find())  # Fetch existing timetable
    return courses_data, lecturer_data, room_data, timetable_data

def create_initial_population(pop_size, courses_data, num_time_slots):
    population = []
    for _ in range(pop_size):
        individual = [-1] * num_time_slots  # Initialize with empty slots
        
        for course_idx, course in enumerate(courses_data):
            credit_hours = course['credit_hours']
            # Ensure at least 2-hour blocks if credit hours > 1
            if credit_hours > 1:
                available_slots = np.random.choice(range(num_time_slots), size=credit_hours, replace=False)
                # Check if the slots can be assigned to the same room
                if all(individual[slot] == -1 for slot in available_slots):
                    for slot in available_slots:
                        individual[slot] = course_idx
            else:  # For single hour courses
                available_slot = np.random.choice(range(num_time_slots))
                if individual[available_slot] == -1:
                    individual[available_slot] = course_idx
        
        population.append(individual)
    return population

# Map the existing timetable data into time slots
def map_existing_timetable(timetable_data, lecturer_data, room_data):
    existing_slots = {'lecturer': {}, 'room': {}}

    for entry in timetable_data:
        day = entry.get('day')
        if day is None:
            print("Missing 'day' in entry:", entry)
            continue  # Skip this entry or handle it appropriately

        # Continue processing if the day is valid
        if day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
            day_idx = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"].index(day)
            start_hour = int(entry['time'].split(":")[0]) - 8  # Map hour to slot index
        slot_idx = day_idx * 9 + start_hour  # Calculate the slot index

        # Track the occupied slots for lecturers and rooms
        lecturer = entry['lecturer']
        room = entry['room']

        if lecturer not in existing_slots['lecturer']:
            existing_slots['lecturer'][lecturer] = set()
        if room not in existing_slots['room']:
            existing_slots['room'][room] = set()

        existing_slots['lecturer'][lecturer].add(slot_idx)
        existing_slots['room'][room].add(slot_idx)

    return existing_slots

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

# Fitness function with existing timetable data consideration
def fitness_func(ga_instance, solution, solution_idx, lecturer_availability, room_data, courses_data, lecturer_data, existing_slots):
    penalty = 0
    lecturer_schedule = {lecturer['username']: [-1] * 45 for lecturer in lecturer_data}
    room_usage = [-1] * 45
    course_counts = {course['course_name']: 0 for course in courses_data}

    for slot_idx, course_idx in enumerate(solution):
        if course_idx == -1:
            continue
        
        course_idx = int(course_idx)
        course = courses_data[course_idx]
        lecturer_name = course['lecturer']
        student_count = course['student_count']
        assigned_room = room_data[slot_idx % len(room_data)]
        
        # Check if the slot is already occupied by the same lecturer or room
        if (slot_idx in existing_slots['lecturer'].get(lecturer_name, set()) or
                slot_idx in existing_slots['room'].get(assigned_room['room_name'], set())):
            penalty += 20  # Strong penalty for conflicts with existing timetable

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

        # Room overlap check
        if room_usage[slot_idx] != -1:
            penalty += 10  # Penalize room conflicts
        else:
            room_usage[slot_idx] = course_idx

        # Check for continuous hour constraint
        if sum(1 for hour in lecturer_schedule[lecturer_name] if hour != -1) > 5:
            penalty += 10  # Penalize exceeding daily limit

        # Track course assignments for credit hour validation
        course_counts[course['course_name']] += 1

    # Validate course credit hours
    for course in courses_data:
        assigned_hours = course_counts[course['course_name']]
        required_hours = course['credit_hours']
        if assigned_hours != required_hours:
            penalty += abs(assigned_hours - required_hours) * 10  # Penalize hour mismatches

    return 1 / (1 + penalty)  # Higher fitness for fewer penalties


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

        # Add missing slots
        elif assigned_hours < required_hours:
            slots_to_add = required_hours - assigned_hours
            for idx in range(len(solution)):
                if solution[idx] == -1:
                    solution[idx] = course_idx
                    slots_to_add -= 1
                    if slots_to_add == 0:
                        break

    # Ensure that all slots assigned to a course are in the same room
    room_assignments = {}
    for slot_idx, course_idx in enumerate(solution):
        if course_idx != -1:
            room_name = room_data[slot_idx % len(room_data)]['room_name']
            if course_idx in room_assignments:
                if room_assignments[course_idx] != room_name:
                    # If a different room is assigned, we need to resolve this
                    solution[slot_idx] = -1  # Clear the conflicting assignment

    return solution

# Run the genetic algorithm
def run_genetic_algorithm():
    courses_data, lecturer_data, room_data, timetable_data = fetch_data()
    num_time_slots = 45  # 9 time slots * 5 days

    lecturer_availability = {lecturer['username']: get_lecturer_availability(lecturer) for lecturer in lecturer_data}
    existing_slots = map_existing_timetable(timetable_data, lecturer_data, room_data)
    gene_space = [-1] + [i for i in range(len(courses_data))]

    def fitness_wrapper(ga_instance, solution, solution_idx):
        return fitness_func(ga_instance, solution, solution_idx, lecturer_availability, room_data, courses_data, lecturer_data, existing_slots)

    def on_generation(ga_instance):
        for idx, solution in enumerate(ga_instance.population):
            ga_instance.population[idx] = repair_solution(solution.copy(), courses_data, room_data)

    ga = pygad.GA(
        num_generations=300,
        sol_per_pop=50,
        num_parents_mating=15,
        fitness_func=fitness_wrapper,
        num_genes=num_time_slots,
        gene_space=gene_space,
        parent_selection_type="tournament",
        crossover_type="single_point",
        mutation_probability=0.2,
        crossover_probability=0.8,
        on_generation=on_generation,
    )
    ga.run()
    solution, fitness, _ = ga.best_solution()
    return solution, fitness

def save_timetable_to_db(solution, courses_data, room_data, lecturer_data):
    timetable = []

    # Create a mapping of lecturer usernames
    lecturer_mapping = {
        lecturer['username']: lecturer['username']
        for lecturer in lecturer_data if 'username' in lecturer
    }

    for slot_idx, course_idx in enumerate(solution):
        if course_idx == -1:
            continue  # Skip empty slots

        course_idx = int(course_idx)
        course_info = courses_data[course_idx]
        lecturer_username = course_info['lecturer']

        # Handle missing lecturer usernames gracefully
        lecturer_name = lecturer_mapping.get(lecturer_username, f"Unknown-{lecturer_username}")

        # Handle missing room names
        assigned_room = room_data[slot_idx % len(room_data)]
        room_name = assigned_room.get('room_name', f"Room-{slot_idx % len(room_data)}")

        # Determine the day and time slot
        day_index = slot_idx // 9  # Calculate day index based on the slot
        day = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"][day_index]
        time_slot = f"{8 + (slot_idx % 9)}:00 - {9 + (slot_idx % 9)}:00"

        # Insert the timetable entry into the database
        timetable_collection.insert_one({
            "course": course_info['course_name'],
            "lecturer": lecturer_name,
            "room": room_name,
            "day": day,
            "time": time_slot
        })

# Execute the algorithm and save the timetable
solution, fitness = run_genetic_algorithm()
# Adjusted to fetch the correct amount of data needed
courses_data, lecturer_data, room_data = fetch_data()[:3]
save_timetable_to_db(solution, courses_data, room_data, lecturer_data)
