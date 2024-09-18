import pygad
import numpy as np

class GeneticAlgorithm:
    def __init__(self, courses, lecturers, rooms, population_size=50, generations=1000, mutation_rate=0.1, crossover_rate=0.8, elitism_count=2):
        self.courses = courses
        self.lecturers = lecturers
        self.rooms = rooms
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.elitism_count = elitism_count
        self.time_slots = [f"{day}-{hour}" for day in DAYS for hour in HOURS]
        self.num_genes = len(courses) * 2  # For each course: time slot and room

    def fitness_function(self, solution, solution_idx):
        timetable = self.decode_chromosome(solution)
        return self.fitness(timetable)

    def run(self):
        ga_instance = pygad.GA(
            num_generations=self.generations,
            num_parents_mating=self.population_size // 2,
            fitness_func=self.fitness_function,
            sol_per_pop=self.population_size,
            num_genes=self.num_genes,
            mutation_percent_genes=self.mutation_rate * 100,
            crossover_probability=self.crossover_rate,
            gene_type=int,  # Genes will be integers representing indices of time slots and rooms
            on_generation=self.callback_generation
        )
        ga_instance.run()

        # Get the best solution after the GA has run
        best_solution, best_solution_fitness, _ = ga_instance.best_solution()
        best_timetable = self.decode_chromosome(best_solution)

        print(f"Best Fitness: {best_solution_fitness}")
        return best_timetable, best_solution_fitness

    def callback_generation(self, ga_instance):
        print(f"Generation {ga_instance.generations_completed}: Best Fitness = {ga_instance.best_solution()[1]}")

    def initialize_population(self):
        # PyGAD handles population initialization, so this is no longer needed
        pass

    def decode_chromosome(self, chromosome):
        """
        Convert a chromosome (array of integers) back to a timetable. 
        Each course is represented by two consecutive genes: time slot and room.
        """
        timetable = []
        for i, course in enumerate(self.courses):
            time_idx = chromosome[2 * i]
            room_idx = chromosome[2 * i + 1]
            time = self.time_slots[time_idx]
            room = list(self.rooms.keys())[room_idx]

            assignment = {
                'course': course['course_name'],
                'lecturer': course['lecturer_name'],
                'room': room,
                'time': time
            }
            timetable.append(assignment)
        return timetable

    def fitness(self, timetable):
        score = 0
        lecturer_schedule = {}
        room_schedule = {}
        for assignment in timetable:
            course = next((c for c in self.courses if c['course_name'] == assignment['course']), None)
            if not course:
                continue
            lecturer = assignment['lecturer']
            room = assignment['room']
            time = assignment['time']
            # Check lecturer availability
            if time in self.lecturers[lecturer]['available_times']:
                score += 1
            # Check room capacity
            if self.rooms[room]['capacity'] >= course['credit_hours']:
                score += 1
            # Check room type
            if self.rooms[room]['room_type'] == course['room_type']:
                score += 1
            # Avoid lecturer conflicts
            lecturer_conflicts = lecturer_schedule.get(lecturer, set())
            if time not in lecturer_conflicts:
                score += 1
                lecturer_conflicts.add(time)
                lecturer_schedule[lecturer] = lecturer_conflicts
            # Avoid room conflicts
            room_conflicts = room_schedule.get(room, set())
            if time not in room_conflicts:
                score += 1
                room_conflicts.add(time)
                room_schedule[room] = room_conflicts
        return score

    def max_fitness(self):
        return len(self.courses) * 5


class TimetableSystem(cmd.Cmd):
    intro = 'Welcome to the Timetable System. Type help or ? to list commands.\n'
    prompt = '(timetable) '

    def __init__(self):
        super().__init__()
        self.lecturers = {}
        self.rooms = {}
        self.courses = []
        self.population_size = 50
        self.generations = 1000
        self.mutation_rate = 0.1
        self.crossover_rate = 0.8
        self.elitism_count = 2

    def do_add_lecturer(self, arg):
        "Add a new lecturer with available times: add_lecturer [name] [available_times (e.g. Mon-8-12,Tue-9-11)]"
        args = arg.split()
        if len(args) < 2:
            print("Please provide the name of the lecturer and their available times.")
            return
        
        name = args[0]
        time_ranges = args[1].split(',')
        available_times = []

        for time_range in time_ranges:
            day, hours = time_range.split('-', 1)
            start_hour, end_hour = map(int, hours.split('-'))
            for hour in range(start_hour, end_hour):
                available_times.append(f"{day}-{hour}")

        self.lecturers[name] = {
            'available_times': available_times
        }
        print(f"Lecturer '{name}' added with available times: {available_times}.")

    
    def do_add_room(self, arg):
        "Add a new room with capacity and type: add_room [room_number] [capacity] [room_type (e.g. Lecture, Lab)]"
        args = arg.split()
        if len(args) != 3:
            print("Please provide the room number, capacity, and room type.")
            return
        
        room_number = args[0]
        try:
            capacity = int(args[1])
        except ValueError:
            print("Capacity must be an integer.")
            return
        room_type = args[2]
        self.rooms[room_number] = {
            'capacity': capacity,
            'room_type': room_type
        }
        print(f"Room '{room_number}' added with capacity {capacity} and type '{room_type}'.")

    def do_add_course(self, arg):
        "Add a new course: add_course [course_name] [lecturer_name] [credit_hours] [room_type]"
        args = arg.split()
        if len(args) != 4:
            print("Please provide course name, lecturer name, credit hours, and room type.")
            return
        
        course_name = args[0]
        lecturer_name = args[1]
        try:
            credit_hours = int(args[2])
        except ValueError:
            print("Credit hours must be an integer.")
            return
        room_type = args[3]

        if lecturer_name not in self.lecturers:
            print(f"Lecturer '{lecturer_name}' does not exist. Add the lecturer first.")
            return

        course = {
            'course_name': course_name,
            'lecturer_name': lecturer_name,
            'credit_hours': credit_hours,
            'room_type': room_type
        }
        self.courses.append(course)
        print(f"Course '{course_name}' added with lecturer '{lecturer_name}', {credit_hours} credit hours, and room type '{room_type}'.")

    def do_view_data(self, arg):
        "View the list of lecturers, rooms, and courses: view_data"
        print("\nLecturers:")
        for lecturer, details in self.lecturers.items():
            print(f"  - {lecturer} (Available Times: {', '.join(details['available_times'])})")
        
        print("\nRooms:")
        for room, details in self.rooms.items():
            print(f"  - {room} (Capacity: {details['capacity']}, Type: {details['room_type']})")
        
        print("\nCourses:")
        for course in self.courses:
            print(f"  - {course['course_name']} (Lecturer: {course['lecturer_name']}, Credit Hours: {course['credit_hours']}, Room Type: {course['room_type']})")

    def do_generate_timetable(self, arg):
        "Generate a timetable using genetic algorithm: generate_timetable"
        if not self.courses or not self.lecturers or not self.rooms:
            print("Please make sure to add courses, lecturers, and rooms before generating the timetable.")
            return
        
        ga = GeneticAlgorithm(self.courses, self.lecturers, self.rooms, self.population_size, self.generations, self.mutation_rate, self.crossover_rate, self.elitism_count)
        best_timetable, fitness = ga.run()
        self.display_timetable(best_timetable)

    def display_timetable(self, timetable):
        organized = {day: {hour: "Free" for hour in HOURS} for day in DAYS}
        
        for assignment in timetable:
            day, hour = assignment['time'].split('-')
            hour = int(hour)
            organized[day][hour] = f"{assignment['course']} ({assignment['lecturer']}, {assignment['room']})"
        
        print("\nGenerated Timetable:")
        for day in DAYS:
            print(f"\n{day}:")
            for hour in HOURS:
                course = organized[day][hour]
                print(f"  {hour}:00 - {course}")

    def do_exit(self, arg):
        "Exit the timetable system: exit"
        print("Exiting the Timetable System.")
        return True


if __name__ == '__main__':
    TimetableSystem().cmdloop()
