import streamlit as st
import pymongo
from pymongo import MongoClient
from geopy.distance import geodesic
import pandas as pd
from datetime import datetime
import hashlib
import folium
from streamlit_folium import folium_static
from bson import ObjectId
import time
import requests
import os
import json
import re

# Page configuration
st.set_page_config(
    page_title="Smart Hospital Bed Allocation System",
    page_icon="🏥",
    layout="wide"
)

# ====================== GEMINI API INTEGRATION ======================
# Get API key from environment variable, fall back to the original key if not set
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyCYDTn-QZC5ZlvX9DGO10fWvk2jz-qyfhI")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

def call_gemini_api(prompt):
    """Call the Gemini API with the given prompt and handle errors"""
    headers = {
        "Content-Type": "application/json"
    }
    
    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ]
    }
    
    # Add API key as query parameter
    url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
    
    try:
        response = requests.post(url, headers=headers, json=data)
        
        # Check if the request was successful
        if response.status_code == 200:
            response_json = response.json()
            # Extract the generated text from the response
            if "candidates" in response_json and len(response_json["candidates"]) > 0:
                if "content" in response_json["candidates"][0]:
                    content = response_json["candidates"][0]["content"]
                    if "parts" in content and len(content["parts"]) > 0:
                        if "text" in content["parts"][0]:
                            return content["parts"][0]["text"]
            
            # If we couldn't extract the text properly
            return "I'm sorry, I couldn't process your question. Please try again."
        else:
            # If API call failed, fall back to local responses
            return get_local_doctor_response(prompt)
            
    except Exception as e:
        # If any error occurs, fall back to local responses
        print(f"API call error: {str(e)}")
        return get_local_doctor_response(prompt)

# Local doctor response implementation as fallback
def get_local_doctor_response(query):
    """Generate a doctor-like response locally instead of using external API."""
    # Dictionary of common symptoms and responses
    responses = {
        "pain": "Pain can be concerning. Can you describe where the pain is located and how severe it is on a scale of 1-10? Is it constant or does it come and go? This information will help me understand your condition better.",
        
        "fever": "A fever is often a sign that your body is fighting an infection. It's important to stay hydrated and rest. If your temperature exceeds 103°F (39.4°C) or persists for more than 3 days, please come in for an examination.",
        
        "headache": "Headaches can have many causes including stress, dehydration, or tension. Try to rest in a quiet, dark room and stay hydrated. If the headache is severe, sudden, or accompanied by other symptoms like confusion or stiff neck, please seek immediate medical attention.",
        
        "cough": "For a cough, I recommend staying hydrated and using honey with warm water (if you're not diabetic and over 1 year old). If you're experiencing shortness of breath, chest pain, or the cough has lasted more than 2 weeks, please schedule an in-person appointment.",
        
        "tired": "Fatigue can be caused by many factors including poor sleep, stress, or underlying medical conditions. Try to maintain a regular sleep schedule and healthy diet. If fatigue persists despite adequate rest, we should investigate further.",
        
        "dizzy": "Dizziness could be related to dehydration, inner ear issues, or blood pressure fluctuations. Sit or lie down immediately when feeling dizzy to prevent falling. Let's schedule you for a check-up to identify the cause.",
        
        "nausea": "For nausea, try eating small, bland meals and staying hydrated with clear fluids. Ginger tea can be helpful for some patients. If vomiting persists more than 24 hours or you see blood, please seek immediate care.",
        
        "medication": "It's very important to take all prescribed medications as directed. If you're experiencing side effects, don't stop taking the medication without consulting with me first - we may need to adjust your dosage or try an alternative.",
        
        "sleep": "Quality sleep is essential for recovery. Try to maintain a regular sleep schedule, avoid screens before bedtime, and keep your room cool and dark. If you're having persistent sleep difficulties, we can discuss sleep hygiene techniques or other interventions.",
    }
    
    # Default responses for when no keywords match
    default_responses = [
        "Thank you for sharing that information. Could you provide more details about your symptoms, including when they started and if anything makes them better or worse?",
        
        "I understand your concern. Based on what you've told me, I recommend monitoring your symptoms for the next 24-48 hours. If they worsen or new symptoms develop, please contact us right away.",
        
        "Your health is important to us. From what you've described, it would be beneficial to schedule an in-person examination to properly assess your condition.",
        
        "I appreciate you reaching out. It's always better to address health concerns promptly. Could you tell me if you have any allergies or current medications?",
        
        "Thank you for your question. While I can provide general guidance, a thorough clinical assessment would give us more accurate information about your condition."
    ]
    
    # Check if any keywords are in the query
    query_lower = query.lower()
    for keyword, response in responses.items():
        if keyword in query_lower:
            return response
    
    # If no match found, return a deterministic but seemingly random default response
    return default_responses[hash(query) % len(default_responses)]

# MongoDB Connection - More reliable implementation
@st.cache_resource
def get_database_connection():
    try:
        # More robust connection string with proper error handling
        client = MongoClient(
            "mongodb+srv://srit:srit@cluster0.ew3gaei.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0",
            serverSelectionTimeoutMS=10000,  # Increased timeout
            connectTimeoutMS=10000,
            socketTimeoutMS=30000  # Increased for long operations
        )
        
        # Test connection by attempting to get server info
        client.server_info()
        
        # Connect to the database explicitly
        db = client.Cluster0
        
        # Test database access by listing collections
        collection_names = db.list_collection_names()
        print(f"Connected to MongoDB. Available collections: {collection_names}")
        
        return db
    except Exception as e:
        print(f"MongoDB connection error details: {str(e)}")
        st.error(f"Failed to connect to MongoDB: {str(e)}")
        # Return None on failure so the application can handle this gracefully
        return None

# Get database connection
db = get_database_connection()

# Hardcoded hospital data - only 3 hospitals
HOSPITALS = [
    {
        "hospital_name": "City Hospital",
        "username": "city_hospital_admin",
        "password": hashlib.sha256("adminpass".encode()).hexdigest(),
        "location": {"latitude": 12.9716, "longitude": 77.5946},
        "total_beds": 100,
        "available_beds": 25,
        "occupied_beds": 75,
        "patients": []
    },
    {
        "hospital_name": "General Hospital",
        "username": "general_hospital_admin",
        "password": hashlib.sha256("adminpass".encode()).hexdigest(),
        "location": {"latitude": 12.9200, "longitude": 77.6200},
        "total_beds": 150,
        "available_beds": 40,
        "occupied_beds": 110,
        "patients": []
    },
    {
        "hospital_name": "Medical Center",
        "username": "medical_center_admin",
        "password": hashlib.sha256("adminpass".encode()).hexdigest(),
        "location": {"latitude": 13.0200, "longitude": 77.5100},
        "total_beds": 80,
        "available_beds": 15,
        "occupied_beds": 65,
        "patients": []
    }
]

# Initialize collections with better error handling and validation
def initialize_collections():
    """
    Initialize database collections if they don't exist
    with proper error handling and transaction support
    """
    if db is None:
        st.sidebar.error("Database connection not available. Cannot initialize collections.")
        return False
    
    try:
        # Get list of existing collections
        existing_collections = db.list_collection_names()
        client = db.client
        
        # Create Users collection if it doesn't exist
        if "users" not in existing_collections:
            try:
                with client.start_session() as session:
                    users_collection = db["users"]
                    # Create default user
                    default_user = {
                        "username": "patient1", 
                        "password": hashlib.sha256("password123".encode()).hexdigest(),
                        "full_name": "Test Patient",
                        "phone": "1234567890",
                        "created_at": datetime.now()
                    }
                    users_collection.insert_one(default_user, session=session)
                    
                    # Create index on username for faster lookups
                    users_collection.create_index("username", unique=True)
                    
                    print("Users collection created successfully")
            except Exception as e:
                print(f"Error creating users collection: {str(e)}")
                return False
        
        # Create Hospitals collection if it doesn't exist
        if "hospitals" not in existing_collections:
            try:
                with client.start_session() as session:
                    hospitals_collection = db["hospitals"]
                    
                    # Insert hospital data within transaction
                    hospitals_collection.insert_many(HOSPITALS, session=session)
                    
                    # Create indexes for faster lookups
                    hospitals_collection.create_index("hospital_name", unique=True)
                    hospitals_collection.create_index("username", unique=True)
                    
                    print("Hospitals collection created successfully")
            except Exception as e:
                print(f"Error creating hospitals collection: {str(e)}")
                return False
        
        # Create Bookings collection if it doesn't exist
        if "bookings" not in existing_collections:
            try:
                bookings_collection = db["bookings"]
                
                # Create indexes for faster lookups
                bookings_collection.create_index([("patient_name", pymongo.ASCENDING), ("phone", pymongo.ASCENDING)])
                bookings_collection.create_index("hospital", pymongo.ASCENDING)
                bookings_collection.create_index("booking_date", pymongo.DESCENDING)
                
                print("Bookings collection created successfully")
            except Exception as e:
                print(f"Error creating bookings collection: {str(e)}")
                return False
        
        # Verify hospitals data consistency
        hospitals_collection = db["hospitals"]
        for hospital in hospitals_collection.find():
            # Ensure patients list exists
            if "patients" not in hospital:
                hospitals_collection.update_one(
                    {"_id": hospital["_id"]},
                    {"$set": {"patients": []}}
                )
                
            # Ensure bed counts are valid
            if "occupied_beds" not in hospital or "available_beds" not in hospital:
                # Calculate occupied beds from patients list if it exists
                occupied = len(hospital.get("patients", []))
                total = hospital.get("total_beds", 100)
                available = total - occupied
                
                hospitals_collection.update_one(
                    {"_id": hospital["_id"]},
                    {"$set": {
                        "occupied_beds": occupied,
                        "available_beds": available
                    }}
                )
                
        return True
        
    except Exception as e:
        st.sidebar.error(f"Error initializing collections: {str(e)}")
        print(f"Database initialization error: {str(e)}")
        return False

# Initialize collections
initialize_collections()

# Session state initialization
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_type' not in st.session_state:
    st.session_state.user_type = None
if 'username' not in st.session_state:
    st.session_state.username = None
if 'hospital_name' not in st.session_state:
    st.session_state.hospital_name = None
if 'patient_latitude' not in st.session_state:
    st.session_state.patient_latitude = None
if 'patient_longitude' not in st.session_state:
    st.session_state.patient_longitude = None
if 'booking_success' not in st.session_state:
    st.session_state.booking_success = False
if 'booking_error' not in st.session_state:
    st.session_state.booking_error = None
if 'booking_details' not in st.session_state:
    st.session_state.booking_details = None
if 'update_success' not in st.session_state:
    st.session_state.update_success = False
if 'update_error' not in st.session_state:
    st.session_state.update_error = None
if 'discharge_success' not in st.session_state:
    st.session_state.discharge_success = False
if 'discharge_error' not in st.session_state:
    st.session_state.discharge_error = None
if 'patient_info' not in st.session_state:
    st.session_state.patient_info = {}
if 'nearest_hospital' not in st.session_state:
    st.session_state.nearest_hospital = None
if 'show_registration' not in st.session_state:
    st.session_state.show_registration = False
# Chatbot session state
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "booking"

# More robust authentication functions
def authenticate_user(username, password):
    """Authenticate a patient user with better error handling"""
    if not username or not password:
        return False
        
    if db is None:
        st.error("Unable to connect to database. Please try again later.")
        return False
        
    try:
        users_collection = db["users"]
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        # Try to find the user with both username and password
        user = users_collection.find_one({"username": username, "password": hashed_password})
        
        return bool(user)  # Returns True if user exists, False otherwise
    except Exception as e:
        print(f"Authentication error: {str(e)}")
        st.error(f"Authentication error occurred. Please try again.")
        return False

def authenticate_hospital(username, password):
    """Authenticate a hospital admin with better error handling"""
    if not username or not password:
        return False
        
    if db is None:
        st.error("Unable to connect to database. Please try again later.")
        return False
        
    try:
        hospitals_collection = db["hospitals"]
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        # Try to find the hospital with both username and password
        hospital = hospitals_collection.find_one({"username": username, "password": hashed_password})
        
        if hospital:
            st.session_state.hospital_name = hospital["hospital_name"]
            return True
        return False
    except Exception as e:
        print(f"Hospital authentication error: {str(e)}")
        st.error(f"Authentication error occurred. Please try again.")
        return False

# Function to create a new patient user account
def register_user(username, password, confirm_password, full_name, phone):
    """Register a new patient user with validation"""
    if db is None:
        st.error("Unable to connect to database. Please try again later.")
        return False, "Database connection error"
        
    # Validate inputs
    if not username or not password or not confirm_password or not full_name or not phone:
        return False, "All fields are required"
        
    if password != confirm_password:
        return False, "Passwords do not match"
        
    if len(password) < 6:
        return False, "Password must be at least 6 characters long"
        
    try:
        users_collection = db["users"]
        
        # Check if username already exists
        existing_user = users_collection.find_one({"username": username})
        if existing_user:
            return False, "Username already exists"
            
        # Hash the password
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        # Create new user document
        new_user = {
            "username": username,
            "password": hashed_password,
            "full_name": full_name,
            "phone": phone,
            "created_at": datetime.now()
        }
        
        # Insert the new user
        result = users_collection.insert_one(new_user)
        
        if result.inserted_id:
            return True, "User registered successfully"
        else:
            return False, "Failed to create user"
            
    except Exception as e:
        print(f"Registration error: {str(e)}")
        return False, f"Registration error occurred: {str(e)}"

# Logout Function
def logout():
    st.session_state.logged_in = False
    st.session_state.user_type = None
    st.session_state.username = None
    st.session_state.hospital_name = None
    st.session_state.patient_latitude = None
    st.session_state.patient_longitude = None
    st.session_state.booking_success = False
    st.session_state.booking_error = None
    st.session_state.booking_details = None
    st.session_state.update_success = False
    st.session_state.update_error = None
    st.session_state.discharge_success = False
    st.session_state.discharge_error = None
    st.session_state.patient_info = {}
    st.session_state.nearest_hospital = None
    st.session_state.chat_history = []
    st.session_state.show_registration = False

# Hospital Selection Logic - Fixed version
def find_nearest_hospital(patient_location, max_distance):
    """
    Find the nearest hospital with available beds within the specified max_distance.
    
    Args:
        patient_location: Tuple of (latitude, longitude)
        max_distance: Maximum distance in kilometers to search
        
    Returns:
        Dictionary with nearest hospital information or None if no hospital found
    """
    if db is None:
        st.error("Database connection not available")
        print("Database connection not available in find_nearest_hospital")
        return None
    
    try:
        print(f"Searching for hospitals within {max_distance}km of {patient_location}")
        
        # Get the hospitals collection
        hospitals_collection = db["hospitals"]
        
        # Explicitly query for hospitals with available beds > 0
        query = {"available_beds": {"$gt": 0}}
        projection = {"hospital_name": 1, "location": 1, "available_beds": 1, "total_beds": 1}
        
        # Execute the query
        hospitals_cursor = hospitals_collection.find(query, projection)
        
        # Convert cursor to list to ensure we have data
        hospitals = list(hospitals_cursor)
        
        print(f"Found {len(hospitals)} hospitals with available beds")
        
        if not hospitals:
            print("No hospitals with available beds found in database")
            return None
            
        # Calculate distances for each hospital
        hospital_distances = []
        
        for hospital in hospitals:
            # Ensure location data exists
            if "location" not in hospital or "latitude" not in hospital["location"] or "longitude" not in hospital["location"]:
                print(f"Hospital {hospital.get('hospital_name', 'Unknown')} has invalid location data")
                continue
                
            hospital_location = (hospital["location"]["latitude"], hospital["location"]["longitude"])
            
            try:
                # Calculate geodesic distance
                distance = geodesic(patient_location, hospital_location).km
                
                print(f"Hospital: {hospital['hospital_name']}, Distance: {distance:.2f}km, Available beds: {hospital['available_beds']}")
                
                # Only include hospitals within the max_distance
                if distance <= max_distance:
                    hospital_distances.append({
                        "name": hospital["hospital_name"],
                        "distance": distance,
                        "available_beds": hospital["available_beds"],
                        "total_beds": hospital.get("total_beds", 0)
                    })
            except Exception as dist_error:
                print(f"Error calculating distance for {hospital.get('hospital_name', 'Unknown')}: {str(dist_error)}")
        
        print(f"Found {len(hospital_distances)} hospitals within {max_distance}km")
        
        if not hospital_distances:
            print(f"No hospitals found within {max_distance}km")
            return None
            
        # Sort hospitals by distance (primary) and available beds (secondary)
        sorted_hospitals = sorted(hospital_distances, key=lambda x: (x["distance"], -x["available_beds"]))
        
        # Return the nearest hospital
        nearest = sorted_hospitals[0]
        print(f"Selected nearest hospital: {nearest['name']} at {nearest['distance']:.2f}km with {nearest['available_beds']} available beds")
        
        return nearest
        
    except Exception as e:
        error_msg = f"Error finding nearest hospital: {str(e)}"
        st.error(error_msg)
        print(error_msg)
        return None

def book_hospital_bed(patient_name, phone, symptoms, hospital_name):
    """
    Book a hospital bed with proper transaction handling and error recovery
    """
    if db is None:
        error_msg = "Database connection not available"
        st.session_state.booking_error = error_msg
        print(error_msg)
        return False
    
    try:
        print(f"Starting booking process for {patient_name} at {hospital_name}")
        
        # Get collections
        hospitals_collection = db["hospitals"]
        bookings_collection = db["bookings"]
        
        # Use a session for better transaction control
        client = hospitals_collection.database.client
        
        with client.start_session() as session:
            # First, check if the hospital exists and has beds - with a direct find to ensure latest data
            hospital = hospitals_collection.find_one(
                {"hospital_name": hospital_name},
                session=session
            )
            
            if not hospital:
                error_msg = f"Hospital {hospital_name} not found"
                st.session_state.booking_error = error_msg
                print(error_msg)
                return False
                
            if hospital.get("available_beds", 0) <= 0:
                error_msg = f"No beds available in {hospital_name}"
                st.session_state.booking_error = error_msg
                print(error_msg)
                return False
            
            # Check if patient is already admitted to this hospital
            patient_already_admitted = False
            if "patients" in hospital and hospital["patients"]:
                for patient in hospital["patients"]:
                    if patient.get("name") == patient_name and patient.get("phone") == phone:
                        patient_already_admitted = True
                        break
                        
            if patient_already_admitted:
                error_msg = f"Patient {patient_name} already admitted to {hospital_name}"
                st.session_state.booking_error = error_msg
                print(error_msg)
                return False
            
            # Format the patient data with proper datetime handling
            patient_data = {
                "name": patient_name,
                "phone": phone,
                "symptoms": symptoms,
                "admission_date": datetime.now()
            }
            
            print(f"Patient data prepared: {patient_data}")
            
            # Create booking record first
            booking_data = {
                "patient_name": patient_name,
                "phone": phone,
                "symptoms": symptoms,
                "hospital": hospital_name,
                "status": "Booked",
                "booking_date": datetime.now()
            }
            
            print(f"Booking data prepared: {booking_data}")
            
            try:
                # Start an explicit transaction
                session.start_transaction()
                
                # Insert booking record
                booking_result = bookings_collection.insert_one(booking_data, session=session)
                booking_id = booking_result.inserted_id
                
                if not booking_id:
                    session.abort_transaction()
                    error_msg = "Failed to create booking record"
                    st.session_state.booking_error = error_msg
                    print(error_msg)
                    return False
                    
                print(f"Booking created with ID: {booking_id}")
                
                # Update hospital with atomic operation - use find_one_and_update for atomicity
                result = hospitals_collection.find_one_and_update(
                    {"hospital_name": hospital_name, "available_beds": {"$gt": 0}},
                    {
                        "$inc": {"available_beds": -1, "occupied_beds": 1},
                        "$push": {"patients": patient_data}
                    },
                    return_document=pymongo.ReturnDocument.AFTER,
                    session=session
                )
                
                if not result:
                    # If update failed, abort the transaction
                    session.abort_transaction()
                    error_msg = "No matching hospital with available beds found"
                    st.session_state.booking_error = error_msg
                    print(f"{error_msg} - transaction aborted")
                    return False
                
                # Commit the transaction
                session.commit_transaction()
                print("Transaction committed successfully")
                
                # Success - set session state for success message
                st.session_state.booking_success = True
                st.session_state.booking_details = {
                    "patient_name": patient_name,
                    "hospital": hospital_name,
                    "booking_id": str(booking_id),
                    "status": "Confirmed",
                    "booking_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                return True
                
            except Exception as tx_error:
                # If any error occurs during transaction, abort it
                if session.in_transaction:
                    session.abort_transaction()
                raise tx_error  # Re-raise to be caught by outer try-except
                    
    except Exception as e:
        error_msg = f"Error during booking: {str(e)}"
        print(f"Exception in booking: {error_msg}")
        st.session_state.booking_error = error_msg
        return False

def discharge_patient(hospital_name, patient_name, patient_phone):
    """
    Discharge a patient with proper error handling and atomic operations
    """
    if db is None:
        error_msg = "Database connection not available"
        st.session_state.discharge_error = error_msg
        print(error_msg)
        return False
    
    try:
        print(f"Starting discharge process for {patient_name} from {hospital_name}")
        
        # Get hospitals collection
        hospitals_collection = db["hospitals"]
        client = hospitals_collection.database.client
        
        with client.start_session() as session:
            try:
                # Start transaction
                session.start_transaction()
                
                # First verify the patient exists
                hospital = hospitals_collection.find_one(
                    {
                        "hospital_name": hospital_name,
                        "patients": {"$elemMatch": {"name": patient_name, "phone": patient_phone}}
                    },
                    session=session
                )
                
                if not hospital:
                    session.abort_transaction()
                    error_msg = f"Patient {patient_name} not found in {hospital_name}"
                    st.session_state.discharge_error = error_msg
                    print(error_msg)
                    return False
                
                # Update bookings collection to mark as discharged
                bookings_collection = db["bookings"]
                booking_update = bookings_collection.update_one(
                    {
                        "patient_name": patient_name,
                        "phone": patient_phone,
                        "hospital": hospital_name,
                        "status": "Booked"
                    },
                    {
                        "$set": {
                            "status": "Discharged",
                            "discharge_date": datetime.now()
                        }
                    },
                    session=session
                )
                
                # Remove patient and update bed counts atomically
                result = hospitals_collection.find_one_and_update(
                    {"hospital_name": hospital_name},
                    {
                        "$pull": {"patients": {"name": patient_name, "phone": patient_phone}},
                        "$inc": {"available_beds": 1, "occupied_beds": -1}
                    },
                    return_document=pymongo.ReturnDocument.AFTER,
                    session=session
                )
                
                if not result:
                    session.abort_transaction()
                    error_msg = "Failed to update hospital data during discharge"
                    st.session_state.discharge_error = error_msg
                    print(error_msg)
                    return False
                
                # Commit transaction
                session.commit_transaction()
                print(f"Successfully discharged {patient_name} from {hospital_name}")
                
                st.session_state.discharge_success = True
                return True
                
            except Exception as tx_error:
                # If any error occurs during transaction, abort it
                if session.in_transaction:
                    session.abort_transaction()
                raise tx_error  # Re-raise to be caught by outer try-except
                
    except Exception as e:
        error_msg = f"Error during patient discharge: {str(e)}"
        print(f"Exception in discharge: {error_msg}")
        st.session_state.discharge_error = error_msg
        return False

# Add these debugging functions to help identify and fix issues
def debug_hospital_data():
    """
    Function to check hospital data structure and integrity
    Use this to troubleshoot when hospital search is not working
    """
    if db is None:
        st.error("Database connection not available")
        return
    
    try:
        hospitals_collection = db["hospitals"]
        all_hospitals = list(hospitals_collection.find())
        
        st.subheader("Hospital Data Debugging")
        st.write(f"Found {len(all_hospitals)} hospitals in database")
        
        if not all_hospitals:
            st.error("No hospitals found in database!")
            st.write("Please check database connection and initialization")
            return
        
        # Check each hospital
        for hospital in all_hospitals:
            st.write("---")
            st.write(f"**Hospital Name:** {hospital.get('hospital_name', 'Missing name!')}")
            
            # Check location data
            if "location" not in hospital:
                st.error("⚠️ Location data missing!")
            else:
                location = hospital["location"]
                if "latitude" not in location or "longitude" not in location:
                    st.error("⚠️ Latitude or longitude missing!")
                else:
                    st.write(f"Location: Lat {location['latitude']}, Long {location['longitude']}")
            
            # Check bed availability
            if "available_beds" not in hospital:
                st.error("⚠️ Available beds data missing!")
            else:
                st.write(f"Available beds: {hospital['available_beds']}")
                
                # Warn if no beds available
                if hospital['available_beds'] <= 0:
                    st.warning("⚠️ No beds available in this hospital")
            
            # Check patients list
            if "patients" not in hospital:
                st.error("⚠️ Patients list missing!")
            else:
                patients = hospital["patients"]
                if not isinstance(patients, list):
                    st.error("⚠️ Patients field is not a list!")
                else:
                    st.write(f"Patients: {len(patients)}")
    
    except Exception as e:
        st.error(f"Error debugging hospital data: {str(e)}")

def repair_hospital_data():
    """
    Function to repair common issues with hospital data
    Use this when hospital search is not working
    """
    if db is None:
        st.error("Database connection not available")
        return False
    
    try:
        hospitals_collection = db["hospitals"]
        all_hospitals = list(hospitals_collection.find())
        
        if not all_hospitals:
            st.error("No hospitals found to repair!")
            return False
        
        repairs_made = 0
        
        # Process each hospital
        for hospital in all_hospitals:
            hospital_id = hospital["_id"]
            updates = {}
            
            # Fix missing location
            if "location" not in hospital:
                # Set default location (Bangalore)
                updates["location"] = {"latitude": 12.9716, "longitude": 77.5946}
            elif "latitude" not in hospital["location"] or "longitude" not in hospital["location"]:
                # Fix incomplete location
                updates["location"] = {"latitude": 12.9716, "longitude": 77.5946}
            
            # Fix bed counts
            patient_count = len(hospital.get("patients", []))
            total_beds = hospital.get("total_beds", 100)
            
            if "available_beds" not in hospital or hospital["available_beds"] < 0:
                # Calculate available beds
                available = max(0, total_beds - patient_count)
                updates["available_beds"] = available
            
            if "occupied_beds" not in hospital or hospital["occupied_beds"] != patient_count:
                # Sync occupied beds with patient count
                updates["occupied_beds"] = patient_count
            
            # Fix total beds if needed
            if "total_beds" not in hospital:
                updates["total_beds"] = 100
            
            # Fix missing patients list
            if "patients" not in hospital:
                updates["patients"] = []
            
            # Apply updates if needed
            if updates:
                result = hospitals_collection.update_one(
                    {"_id": hospital_id},
                    {"$set": updates}
                )
                if result.modified_count > 0:
                    repairs_made += 1
        
        if repairs_made > 0:
            st.success(f"Repaired {repairs_made} hospital records")
            return True
        else:
            st.info("No repairs needed")
            return True
    
    except Exception as e:
        st.error(f"Error repairing hospital data: {str(e)}")
        return False

# Add this to the sidebar for admin access
def add_debug_tools_to_sidebar():
    """Add debugging tools to the sidebar for administrators"""
    st.sidebar.subheader("Admin Tools")
    
    # Only show for hospital admins
    if st.session_state.logged_in and st.session_state.user_type == "hospital":
        if st.sidebar.button("Debug Hospital Data"):
            debug_hospital_data()
        
        if st.sidebar.button("Repair Hospital Data"):
            success = repair_hospital_data()
            if success:
                st.sidebar.success("Repair completed")
                # Force a page refresh to see changes
                st.rerun()
            else:
                st.sidebar.error("Repair failed")

# Chatbot Interface - Simplified version without suggested questions
def display_chatbot_interface():
    st.header("🏥 Ask a Healthcare Provider")
    st.write("Type your healthcare question below.")
    st.info("This AI assistant can provide general medical information. For urgent concerns, please contact your actual healthcare provider.")

    # Display chat history with simple styling
    st.subheader("Your Conversation")
    chat_container = st.container(height=400, border=True)
    with chat_container:
        if not st.session_state.chat_history:
            st.write("👋 Hello! Please type your healthcare question below.")
        
        for message in st.session_state.chat_history:
            role_label = "You" if message["role"] == "user" else "Healthcare Provider"
            
            if message["role"] == "user":
                st.markdown(f"<div style='background-color:#f0f2f6;padding:10px;border-radius:10px;margin-bottom:10px'><strong>{role_label}:</strong> {message['content']}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='background-color:#e1f5fe;padding:10px;border-radius:10px;margin-bottom:10px'><strong>{role_label}:</strong> {message['content']}</div>", unsafe_allow_html=True)
    
    # Get user input with direct prompt
    user_input = st.chat_input("Type your healthcare question here...")
    
    if user_input:
        # Add user message to chat history
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        
        # Show typing indicator
        with st.spinner("Getting a response..."):
            # Get AI response with healthcare provider prompt
            prompt = f"""You are a helpful healthcare provider assistant responding to a patient's question.
            Provide accurate, clear, and concise medical information.
            Use simple language and be supportive in your response.
            
            Patient asks: {user_input}
            
            Your response:"""
            
            try:
                # Try API call first
                ai_response = call_gemini_api(prompt)
                # If response is empty or error message, fall back to local
                if not ai_response or "couldn't process" in ai_response:
                    ai_response = get_local_doctor_response(user_input)
            except:
                # If any exception occurs, use local response
                ai_response = get_local_doctor_response(user_input)
                
            time.sleep(0.5)  # Minimal thinking time
        
        # Add AI response to chat history
        st.session_state.chat_history.append({"role": "assistant", "content": ai_response})
        st.rerun()
    
    # Buttons for chat management with simple labels
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Start New Chat", help="Clear this conversation"):
            st.session_state.chat_history = []
            st.rerun()
    
    # Hospital information section - simplified
    st.markdown("---")
    
    # Simple hospital information
    st.subheader("Hospital Information")
    
    info_cols = st.columns(2)
    
    with info_cols[0]:
        st.markdown("""
        **Important Numbers:**
        - Nurse Station: 123
        - Hospital Info: 456
        - Food Service: 789
        """)
    
    with info_cols[1]:
        st.markdown("""
        **Daily Schedule:**
        - Breakfast: 7:30 AM
        - Lunch: 12:00 PM
        - Dinner: 6:00 PM
        - Quiet Hours: 10 PM - 6 AM
        """)

# Patient Registration Interface
def display_registration_interface():
    st.subheader("Create a Patient Account")
    
    with st.form("registration_form"):
        username = st.text_input("Username", placeholder="Choose a username")
        full_name = st.text_input("Full Name", placeholder="Enter your full name")
        phone = st.text_input("Phone Number", placeholder="Enter your phone number")
        
        password = st.text_input("Password", type="password", placeholder="Choose a password (min 6 characters)")
        confirm_password = st.text_input("Confirm Password", type="password", placeholder="Confirm your password")
        
        submit_button = st.form_submit_button("Register")
    
    if submit_button:
        # Validate inputs
        if not username or not password or not confirm_password or not full_name or not phone:
            st.error("All fields are required")
            return
        
        if password != confirm_password:
            st.error("Passwords do not match")
            return
        
        if len(password) < 6:
            st.error("Password must be at least 6 characters long")
            return
        
        # Call registration function
        success, message = register_user(username, password, confirm_password, full_name, phone)
        
        if success:
            st.success(message)
            st.info("You can now log in with your new account")
            st.session_state.show_registration = False
        else:
            st.error(message)

# Patient Booking Interface
def display_booking_interface():
    st.header("📝 Book a Hospital Bed")
    
    # Show booking result if available
    if st.session_state.booking_success:
        st.success("Hospital bed booked successfully! 🎉")
        st.balloons()
        
        # Display detailed booking information
        if st.session_state.booking_details:
            st.subheader("🎫 Booking Details")
            details = st.session_state.booking_details
            st.info(f"""
            ✅ **Booking Confirmed!**
            
            **Patient Name:** {details['patient_name']}
            **Hospital:** {details['hospital']}
            **Booking ID:** {details['booking_id']}
            **Status:** {details['status']}
            **Booking Time:** {details['booking_time']}
            
            Please proceed to the hospital with your ID proof and booking ID.
            """)
        
        # Add a button to make a new booking
        if st.button("Make a New Booking"):
            st.session_state.booking_success = False
            st.session_state.booking_details = None
            st.session_state.patient_info = {}
            st.session_state.nearest_hospital = None
            st.rerun()
        
        # Return early to avoid showing the booking form
        return
    
    if st.session_state.booking_error:
        st.error(f"⚠️ Booking failed: {st.session_state.booking_error}")
        # Don't reset the error here - we'll do it after displaying the form
    
    # Patient Details Form
    with st.form("patient_details_form"):
        st.subheader("Patient Details")
        
        # Pre-fill form fields if we have data in session state
        patient_name = st.text_input("Full Name", value=st.session_state.patient_info.get("name", ""), placeholder="Enter patient name")
        phone = st.text_input("Phone Number", value=st.session_state.patient_info.get("phone", ""), placeholder="Enter contact number")
        symptoms = st.text_area("Symptoms", value=st.session_state.patient_info.get("symptoms", ""), placeholder="Describe symptoms briefly")
        
        # Location capture
        st.subheader("📍 Patient Location")
        location_col1, location_col2 = st.columns(2)
        with location_col1:
            latitude = st.number_input("Latitude", value=st.session_state.patient_latitude or 12.97, format="%.4f", 
                                       help="Your current latitude - you can use Google Maps to find your coordinates")
        with location_col2:
            longitude = st.number_input("Longitude", value=st.session_state.patient_longitude or 77.59, format="%.4f",
                                        help="Your current longitude - you can use Google Maps to find your coordinates")
        
        search_radius = st.slider("Search Distance (km)", min_value=5, max_value=50, value=10, step=5,
                                 help="Maximum distance to search for hospitals")
        
        find_hospital = st.form_submit_button("Find Nearest Hospital")
    
    # Reset error after displaying the form
    if st.session_state.booking_error:
        st.session_state.booking_error = None
    
    # Process form submission
    if find_hospital:
        if not all([patient_name, phone, symptoms]):
            st.error("Please fill in all patient details!")
        else:
            # Save patient info to session state
            st.session_state.patient_info = {
                "name": patient_name,
                "phone": phone, 
                "symptoms": symptoms
            }
            
            st.session_state.patient_latitude = latitude
            st.session_state.patient_longitude = longitude
            
            # Find nearest hospital with detailed progress updates
            with st.spinner("Searching for hospitals with available beds..."):
                patient_location = (latitude, longitude)
                
                st.info(f"Looking for hospitals within {search_radius}km of your location...")
                
                # Try to find hospital within initial radius
                nearest_hospital = find_nearest_hospital(patient_location, search_radius)
                
                # If no hospital found, try with increasing radius
                if not nearest_hospital:
                    for radius in [20, 30, 50]:
                        if radius > search_radius:  # Only try larger radii
                            st.info(f"No hospitals found within {search_radius}km. Expanding search to {radius}km...")
                            nearest_hospital = find_nearest_hospital(patient_location, radius)
                            if nearest_hospital:
                                break
                
                # Save result to session state
                st.session_state.nearest_hospital = nearest_hospital
            
            # Force refresh to show the hospital data
            st.rerun()
    
    # Display hospital information if we have it
    if st.session_state.nearest_hospital:
        nearest_hospital = st.session_state.nearest_hospital
        st.success(f"Nearest hospital found: {nearest_hospital['name']} (Distance: {nearest_hospital['distance']:.2f} km)")
        
        # Display hospital details and booking option with better styling
        st.subheader("Hospital Details")
        
        # Create metrics for hospital details
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Hospital", nearest_hospital['name'])
        with col2:
            st.metric("Distance", f"{nearest_hospital['distance']:.2f} km")
        with col3:
            st.metric("Available Beds", nearest_hospital['available_beds'])
        
        # Show hospital on map
        if db is not None:
            try:
                hospital_info = db["hospitals"].find_one({"hospital_name": nearest_hospital['name']})
                if hospital_info:
                    m = folium.Map(location=[st.session_state.patient_latitude, st.session_state.patient_longitude], zoom_start=12)
                    
                    # Add patient marker
                    folium.Marker(
                        [st.session_state.patient_latitude, st.session_state.patient_longitude],
                        popup="Your Location",
                        icon=folium.Icon(color="blue", icon="user")
                    ).add_to(m)
                    
                    # Add hospital marker
                    hospital_lat = hospital_info["location"]["latitude"]
                    hospital_lon = hospital_info["location"]["longitude"]
                    folium.Marker(
                        [hospital_lat, hospital_lon],
                        popup=hospital_info["hospital_name"],
                        icon=folium.Icon(color="red", icon="plus")
                    ).add_to(m)
                    
                    # Add line between points
                    folium.PolyLine(
                        [(st.session_state.patient_latitude, st.session_state.patient_longitude), 
                         (hospital_lat, hospital_lon)],
                        color="green",
                        weight=2,
                        opacity=1
                    ).add_to(m)
                    
                    # Display map
                    st.subheader("📍 Location Map")
                    folium_static(m)
            except Exception as map_error:
                st.error(f"Error displaying map: {str(map_error)}")
        
        # Confirm booking button with progress indicator
        st.subheader("Confirm Booking")
        st.info("Review the details above and confirm your booking")
        
        if st.button("Book Now", use_container_width=True):
            with st.spinner("Processing your booking..."):
                patient_name = st.session_state.patient_info["name"]
                phone = st.session_state.patient_info["phone"]  
                symptoms = st.session_state.patient_info["symptoms"]
                
                print(f"Book Now button clicked - patient: {patient_name}, hospital: {nearest_hospital['name']}")
                
                # Call the booking function
                booking_success = book_hospital_bed(
                    patient_name=patient_name,
                    phone=phone,
                    symptoms=symptoms,
                    hospital_name=nearest_hospital['name']
                )
                
                print(f"Booking result: {booking_success}")
                
                if booking_success:
                    st.rerun()  # Refresh to show the success message
                else:
                    # Error will be shown at the top
                    st.rerun()
    elif find_hospital:  # If we tried to find a hospital but failed
        st.error("No hospitals with available beds found within the search distance. Please try increasing the search radius or try again later.")

# Patient Interface with Tabs
def display_patient_interface():
    # Add tabs for different patient functions
    tab1, tab2 = st.tabs(["📝 Book Hospital Bed", "🩺 Virtual Doctor"])
    
    with tab1:
        display_booking_interface()
    
    with tab2:
        display_chatbot_interface()

# Hospital Admin Interface with improved error handling and CRUD operations
def display_hospital_interface():
    st.header(f"🏥 {st.session_state.hospital_name} Dashboard")
    
    # Check for notification states and display them
    if st.session_state.update_success:
        st.success("✅ Hospital bed count updated successfully!")
        st.session_state.update_success = False  # Reset after showing
    
    if st.session_state.update_error:
        st.error(f"⚠️ Update failed: {st.session_state.update_error}")
        st.session_state.update_error = None  # Reset after showing
        
    if st.session_state.discharge_success:
        st.success("✅ Patient discharged successfully!")
        st.session_state.discharge_success = False  # Reset after showing
        
    if st.session_state.discharge_error:
        st.error(f"⚠️ Discharge failed: {st.session_state.discharge_error}")
        st.session_state.discharge_error = None  # Reset after showing
    
    # Always fetch fresh data directly from MongoDB
    if db is None:
        st.error("Database connection not available. Unable to fetch hospital data.")
        return
    
    try:
        # Use a fresh query with no caching to get latest data
        hospitals_collection = db["hospitals"]
        hospital_data = hospitals_collection.find_one({"hospital_name": st.session_state.hospital_name})
        
        if not hospital_data:
            st.error("Hospital data not found!")
            return
        
        # Dashboard metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Beds", hospital_data["total_beds"])
        with col2:
            st.metric("Available Beds", hospital_data["available_beds"])
        with col3:
            st.metric("Occupied Beds", hospital_data["occupied_beds"])
        with col4:
            occupancy_rate = (hospital_data["occupied_beds"] / hospital_data["total_beds"]) * 100
            st.metric("Occupancy Rate", f"{occupancy_rate:.1f}%")
        
        # Add update available beds functionality
        st.subheader("Update Bed Count")
        with st.form("update_beds_form"):
            new_available = st.number_input("Update Available Beds", 
                                         min_value=0, 
                                         max_value=hospital_data["total_beds"],
                                         value=hospital_data["available_beds"])
            
            update_beds = st.form_submit_button("Update Bed Count")
            
        if update_beds:
            try:
                # Only proceed if there's an actual change
                if new_available != hospital_data["available_beds"]:
                    # Calculate new occupied count
                    new_occupied = hospital_data["total_beds"] - new_available
                    
                    # Prevent setting available beds lower than physical possibility
                    patient_count = len(hospital_data.get("patients", []))
                    if new_occupied < patient_count:
                        st.session_state.update_error = f"Cannot set occupied beds lower than current patient count ({patient_count})"
                        st.rerun()
                    
                    # Update in database with atomic operation
                    client = hospitals_collection.database.client
                    with client.start_session() as session:
                        update_result = hospitals_collection.find_one_and_update(
                            {"hospital_name": st.session_state.hospital_name},
                            {"$set": {"available_beds": new_available, "occupied_beds": new_occupied}},
                            return_document=pymongo.ReturnDocument.AFTER,
                            session=session
                        )
                        
                        if update_result:
                            st.session_state.update_success = True
                            st.rerun()
                        else:
                            st.session_state.update_error = "Failed to update bed count"
                            st.rerun()
                else:
                    st.session_state.update_error = "No changes were made to bed count"
                    st.rerun()
            except Exception as e:
                st.session_state.update_error = f"Error updating bed count: {str(e)}"
                st.rerun()
        
        # Recent Bookings
        st.subheader("Recent Bookings")
        bookings_collection = db["bookings"]
        recent_bookings = list(bookings_collection.find(
            {"hospital": st.session_state.hospital_name}
        ).sort("booking_date", pymongo.DESCENDING).limit(5))
        
        if recent_bookings:
            for booking in recent_bookings:
                # Convert ObjectId to string and format date
                booking_id = str(booking["_id"])
                booking_date = booking["booking_date"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(booking["booking_date"], datetime) else booking["booking_date"]
                
                # Create an expandable section for each booking
                with st.expander(f"Booking: {booking['patient_name']} - {booking_date}"):
                    st.write(f"**Patient:** {booking['patient_name']}")
                    st.write(f"**Phone:** {booking['phone']}")
                    st.write(f"**Symptoms:** {booking['symptoms']}")
                    st.write(f"**Status:** {booking['status']}")
                    st.write(f"**Booking ID:** {booking_id}")
        else:
            st.info("No recent bookings found.")
        
        # Patients List
        st.subheader("Admitted Patients")
        if "patients" in hospital_data and hospital_data["patients"]:
            # Convert to list if it's not already
            patients_list = hospital_data["patients"] if isinstance(hospital_data["patients"], list) else []
            
            if patients_list:
                # Fix date format for display
                for patient in patients_list:
                    if "admission_date" in patient:
                        if isinstance(patient["admission_date"], datetime):
                            patient["admission_date"] = patient["admission_date"].strftime("%Y-%m-%d %H:%M:%S")
                
                patients_df = pd.DataFrame(patients_list)
                # Clean up display columns
                display_cols = [col for col in patients_df.columns if col != '_id']
                
                st.dataframe(patients_df[display_cols], use_container_width=True)
                
                # Add discharge patient functionality with improved error handling
                st.subheader("Discharge Patient")
                
                # Create a more robust patient selection system
                if "name" in patients_df.columns and "phone" in patients_df.columns:
                    patient_options = [f"{row['name']} ({row['phone']})" for _, row in patients_df.iterrows()]
                    patient_options = ["Select a patient"] + patient_options
                    
                    if len(patient_options) > 1:  # If we have patients
                        selected_patient_option = st.selectbox("Select Patient to Discharge", patient_options)
                        
                        if selected_patient_option != "Select a patient":
                            # Extract name and phone from the selection
                            match = re.match(r"(.*) \((.*)\)$", selected_patient_option)
                            if match:
                                selected_name = match.group(1)
                                selected_phone = match.group(2)
                                
                                with st.form("discharge_form"):
                                    st.write(f"Are you sure you want to discharge {selected_name}?")
                                    confirm_discharge = st.form_submit_button("Confirm Discharge")
                                
                                if confirm_discharge:
                                    # Call the improved discharge function
                                    discharge_result = discharge_patient(
                                        hospital_name=st.session_state.hospital_name,
                                        patient_name=selected_name,
                                        patient_phone=selected_phone
                                    )
                                    
                                    if discharge_result:
                                        st.rerun()  # Refresh to show updated data
                else:
                    st.error("Patient data is missing required fields (name and phone)")
            else:
                st.info("No patients currently admitted.")
        else:
            st.info("No patients currently admitted.")
            
    except Exception as e:
        st.error(f"Error displaying hospital interface: {str(e)}")
        print(f"Hospital interface error: {str(e)}")  # Log for debugging

# Add this utility function to help with location
def get_current_location():
    """
    Helper function to get current location using browser geolocation API
    Note: This is just a stub - actual implementation would require JavaScript integration
    """
    # This is where you would implement browser geolocation
    # For now, we return a default Bangalore location
    return (12.9716, 77.5946)

# Main App UI with improved logic and debug tools
def main():
    st.title("🏥 Smart Hospital Bed Allocation System")
    
    # Show MongoDB connection status
    if db is None:
        st.error("⚠️ Database connection failed. Some features may not work correctly.")
    else:
        # Initialize collections quietly - only show errors
        init_result = initialize_collections()
        if not init_result:
            st.warning("⚠️ There was an issue initializing the database. Some features may be limited.")
    
    # Sidebar for login/logout and registration
    with st.sidebar:
        st.header("User Controls")
        
        if st.session_state.logged_in:
            st.success(f"Logged in as: {st.session_state.username} ({st.session_state.user_type})")
            if st.session_state.user_type == "hospital":
                st.info(f"Hospital: {st.session_state.hospital_name}")
            
            if st.button("Logout"):
                logout()
                st.rerun()
                
            # Add debug tools for hospital admins
            if st.session_state.user_type == "hospital":
                add_debug_tools_to_sidebar()
        else:
            if st.session_state.show_registration:
                # Show the registration interface
                display_registration_interface()
                
                # Add a button to go back to login
                if st.button("Back to Login"):
                    st.session_state.show_registration = False
                    st.rerun()
            else:
                # Show the login interface
                login_type = st.radio("Select Login Type:", ["Patient", "Hospital Admin"])
                
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("Login"):
                        if login_type == "Patient":
                            if authenticate_user(username, password):
                                st.session_state.logged_in = True
                                st.session_state.user_type = "patient"
                                st.session_state.username = username
                                st.rerun()
                            else:
                                st.error("Invalid credentials!")
                        else:  # Hospital Admin
                            if authenticate_hospital(username, password):
                                st.session_state.logged_in = True
                                st.session_state.user_type = "hospital"
                                st.session_state.username = username
                                st.rerun()
                            else:
                                st.error("Invalid credentials!")
                
                with col2:
                    if st.button("Register") and login_type == "Patient":
                        st.session_state.show_registration = True
                        st.rerun()
    
    # Main Content Area
    if not st.session_state.logged_in:
        # Landing page when not logged in
        st.info("Please login to access the system.")
        
        # Display system features
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Patient Features")
            st.markdown("""
            - Book hospital bed based on your location
            - Automatically find nearest hospital
            - Secure booking confirmation
            - Virtual doctor consultation via chatbot
            - Ward room availability check
            """)
        
        with col2:
            st.subheader("Hospital Admin Features")
            st.markdown("""
            - Manage bed availability
            - View admitted patients
            - Track hospital occupancy
            - Process patient discharges
            - View recent bookings
            """)
        
        # Add debug login credentials - only for development/testing
        st.markdown("---")
        st.subheader("Demo Accounts")
        st.markdown("""
        **Patient Login:**
        - Username: patient1
        - Password: password123
        
        **Hospital Admin Login:**
        - Username: city_hospital_admin
        - Password: adminpass
        """)
    
    else:
        # User is logged in - show appropriate interface
        if st.session_state.user_type == "patient":
            display_patient_interface()
        else:  # hospital admin
            display_hospital_interface()

if __name__ == "__main__":
    main()