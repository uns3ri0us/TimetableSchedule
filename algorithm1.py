import pygad
import numpy as np
from flask import session
from pymongo import MongoClient
from database import courses_collection, users_collection, rooms_collection, timetable_collection  # Import collections

# Fetch courses and lecturer availability
def fetch_data():
    courses_data = list(courses_collection.find())  # Fetch new semester courses
    lecturer_data = list(users_collection.find({'role': 'lecturer'}))  # Fetch only lecturers
    room_data = list(rooms_collection.find())  # Fetch all rooms
    return courses_data, lecturer_data, room_data

# Extract course names and number of courses
courses_data, lecturer_data, room_data = fetch_data()
courses = [course['course_name'] for course in courses_data]
num_courses = len(courses)

def create_initial_population(pop_size, courses_data, num_time_slots):
    population = []
    for _ in range(pop_size):
        individual = [-1] * num_time_slots  # Initialize with empty slots (-1 means no course)
        
        # Assign each course to a number of slots equal to its credit hours
        for course_idx, course in enumerate(courses_data):
            credit_hours = course['credit_hours']
            
            # Randomly assign the course to available time slots
            available_slots = np.random.choice(range(num_time_slots), size=credit_hours, replace=False)
            for slot in available_slots:
                individual[slot] = course_idx  # Assign course index to this time slot
        
        population.append(individual)
    
    return population

# Lecturer availability (transform availability into time slots)
def get_lecturer_availability(lecturer):
    availability = lecturer.get('availability', {})
    available_slots = []
    days_mapping = {"monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4, "friday": 5}

    for day, times in availability.items():
        if day in days_mapping:
            day_index = days_mapping[day]
            if isinstance(times, str):
                try:
                    start_time, end_time = map(lambda t: int(t.split(":")[0]), times.split("-"))
                    for hour in range(start_time, end_time):
                        slot_index = (day_index - 1) * 9 + hour - 8
                        available_slots.append(slot_index)
                except ValueError:
                    print(f"Error parsing time for lecturer {lecturer['username']} on {day}")
            elif isinstance(times, list):
                for time_range in times:
                    try:
                        start_time, end_time = map(lambda t: int(t.split(":")[0]), time_range.split("-"))
                        for hour in range(start_time, end_time):
                            slot_index = (day_index - 1) * 9 + hour - 8
                            available_slots.append(slot_index)
                    except ValueError:
                        print(f"Error parsing time range {time_range} for lecturer {lecturer['username']} on {day}")
    return available_slots

def fitness_func(ga_instance, solution, solution_idx, lecturer_availability):
    penalty = 0
    course_counts = {course['course_name']: 0 for course in courses_data}

    # Check for course overlaps, lecturer availability, and room assignment
    for slot_idx, course_idx in enumerate(solution):
        if course_idx == -1:
            continue  # No course assigned in this time slot
        
        course_info = courses_data[course_idx]
        lecturer_name = course_info['lecturer']
        lecturer_pref = lecturer_availability.get(lecturer_name, [])
        
        # Check if the lecturer is available in this slot
        if slot_idx not in lecturer_pref:
            penalty += 5  # Penalize if lecturer is not available
        
        # Count how many times each course is scheduled
        course_counts[course_info['course_name']] += 1
    
    # Apply penalties for courses not matching their credit hours
    for course in courses_data:
        course_name = course['course_name']
        scheduled_hours = course_counts[course_name]
        required_hours = course['credit_hours']
        
        if scheduled_hours < required_hours:
            penalty += (required_hours - scheduled_hours) * 5  # Penalize for under-scheduling
        elif scheduled_hours > required_hours:
            penalty += (scheduled_hours - required_hours) * 5  # Penalize for over-scheduling
    
    # Room assignment and capacity checking (same as before)
    for slot_idx, course_idx in enumerate(solution):
        if course_idx == -1:
            continue
        
        course_info = courses_data[course_idx]
        student_count = course_info['student_count']
        assigned_room = room_data[slot_idx % len(room_data)]
        room_capacity = assigned_room['capacity']
        
        if student_count > room_capacity:
            penalty += 10  # Penalize if room is too small
    
    return 1 / (1 + penalty)

# Genetic Algorithm configuration
def run_genetic_algorithm(courses_data, lecturer_data, room_data):
    courses = [course['course_name'] for course in courses_data]
    num_courses = len(courses)
    num_time_slots = 45  # 9 time slots per day * 5 days
    
    # Create lecturer availability dictionary
    lecturer_availability = {lecturer['username']: get_lecturer_availability(lecturer) for lecturer in lecturer_data}

    # Define a wrapper fitness function to pass lecturer_availability
    def fitness_wrapper(ga_instance, solution, solution_idx):
        return fitness_func(ga_instance, solution, solution_idx, lecturer_availability)

    # Genetic Algorithm configuration
    ga = pygad.GA(num_generations=100,
              num_parents_mating=10,
              fitness_func=fitness_wrapper,  # Pass the wrapped fitness function
              sol_per_pop=20,
              num_genes=num_time_slots,
              gene_type=int,
              init_range_low=0,
              init_range_high=num_courses-1,
              parent_selection_type="rank",
              keep_parents=1,
              crossover_probability=0.9,
              mutation_probability=0.1)
    
    # Run the genetic algorithm
    ga.run()

    # Retrieve the best solution found by the GA
    solution, fitness, _ = ga.best_solution()
    
    # Return the best timetable and its fitness score
    return solution, fitness

# Function to generate the detailed timetable based on the GA solution
def generate_detailed_timetable(solution, courses_data, room_data):
    detailed_timetable = []
    
    for slot_idx, course_idx in enumerate(solution):
        course_info = courses_data[course_idx]
        assigned_room = room_data[slot_idx % len(room_data)]
        room_name = assigned_room['room_name']
        
        day = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"][slot_idx // 9]
        time_slot = f"{8 + (slot_idx % 9)}:00 - {9 + (slot_idx % 9)}:00"

        timetable_collection.insert_one({
            "course": course_info['course_name'],
            "lecturer": course_info['lecturer'],
            "room": room_name,
            "day": day,
            "time": time_slot
        })

    return detailed_timetable