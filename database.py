from pymongo import MongoClient

# MongoDB connection setup
client = MongoClient('mongodb://localhost:27017/')
db = client['college_timetable']

# MongoDB collections
courses_collection = db['courses']
users_collection = db['users']
rooms_collection = db['rooms']
timetable_collection = db['timetables']

__all__ = ['courses_collection', 'users_collection', 'rooms_collection', 'timetable_collection']
