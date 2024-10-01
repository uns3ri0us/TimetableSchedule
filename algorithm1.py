import pygad
import numpy as np

# Function to run the genetic algorithm for timetable generation
def run_genetic_algorithm(courses_data, num_time_slots=10):
    num_courses = len(courses_data)

    # Fitness function
    def fitness_func(solution, solution_idx):
        penalty = 0
        course_counts = {course['_id']: 0 for course in courses_data}
        for slot in solution:
            course_counts[courses_data[slot]['_id']] += 1
        for count in course_counts.values():
            if count > 1:
                penalty += count - 1
        return 1 / (1 + penalty)  # Minimize penalty for scheduling conflicts

    # Create Genetic Algorithm instance
    ga = pygad.GA(num_generations=100,
                  num_parents_mating=10,
                  fitness_func=fitness_func,
                  sol_per_pop=20,
                  num_genes=num_time_slots,
                  gene_type=int,
                  init_range_low=0,
                  init_range_high=num_courses - 1,
                  parent_selection_type="rank",
                  keep_parents=1,
                  crossover_probability=0.9,
                  mutation_probability=0.1)

    # Run the genetic algorithm
    ga.run()

    # Retrieve the best solution
    solution, fitness, _ = ga.best_solution()

    # Prepare detailed timetable data
    timetable = []
    for slot_idx, course_idx in enumerate(solution):
        course_info = courses_data[course_idx]
        # Example time slot logic
        day = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"][slot_idx // 9]
        time_slot = f"{8 + (slot_idx % 9)}:00 - {9 + (slot_idx % 9)}:00"
        
        timetable.append({
            "course": course_info['course_name'],
            "lecturer": course_info['lecturer'],
            "room": "LR401",  # Example, room assignment can be more dynamic
            "day": day,
            "time": time_slot
        })

    return timetable, fitness
