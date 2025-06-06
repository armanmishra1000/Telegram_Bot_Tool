import os
import urllib.parse
import logging
from pymongo import MongoClient # Corrected import casing
from pymongo.server_api import ServerApi
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, OperationFailure
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List, Tuple
from flask_login import UserMixin
from werkzeug.security import check_password_hash
from bson import ObjectId
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import OperationFailure

# --- Load Environment Variables ---
load_dotenv()

# --- Configuration ---
DATABASE_NAME = "Telegrambot"      
COLLECTION_NAME = "user_files"     

# --- MongoDB Connection Setup ---
_client: Optional[MongoClient] = None
_db: Optional[Database] = None
_collection: Optional[Collection] = None

def _connect_to_db() -> Tuple[Optional[MongoClient], str]:
    """
    Establishes a connection to MongoDB Atlas using environment variables.
    Returns the client instance and an error message if connection fails.
    """
    global _client # Allow modification of the global variable

    if _client is not None:
         return _client, "" 


    ATLAS_USER = os.getenv("ATLAS_USER")
    ATLAS_PASSWORD = os.getenv("ATLAS_PASSWORD")
    ATLAS_CLUSTER_HOST = os.getenv("ATLAS_CLUSTER_HOST")
    print(f"--- DEBUG: Connecting with HOST = '{ATLAS_CLUSTER_HOST}' ---")

    if not ATLAS_USER: 
         error_msg = "Database Error: ATLAS_USER environment variable not set or empty."
         logging.critical(error_msg)
         return None, error_msg
    if not ATLAS_PASSWORD: 
         error_msg = "Database Error: ATLAS_PASSWORD environment variable not set or empty."
         logging.critical(error_msg)
         return None, error_msg
    if not ATLAS_CLUSTER_HOST: 
         error_msg = "Database Error: ATLAS_CLUSTER_HOST environment variable not set or empty."
         logging.critical(error_msg)
         return None, error_msg
    
    encoded_user = urllib.parse.quote_plus(ATLAS_USER)
    encoded_password = urllib.parse.quote_plus(ATLAS_PASSWORD)
    
    try:
        
        encoded_user = urllib.parse.quote_plus(ATLAS_USER)
        encoded_password = urllib.parse.quote_plus(ATLAS_PASSWORD)

        CONNECTION_STRING = f"mongodb+srv://{encoded_user}:{encoded_password}@{ATLAS_CLUSTER_HOST}/?retryWrites=true&w=majority&appName=Telegrambot"

        logging.info(f"Attempting to connect to MongoDB Atlas host: {ATLAS_CLUSTER_HOST}...")
        client = MongoClient(CONNECTION_STRING, server_api=ServerApi('1'))

        # Ping to confirm connection
        client.admin.command('ping')
        logging.info("✅ Successfully connected and pinged MongoDB Atlas!")
        _client = client 
        return _client, "" 

    except ConnectionFailure as cf:
        error_msg = f"MongoDB Connection Failure: {cf}"
        logging.error(error_msg)
        return None, error_msg
    except OperationFailure as of: 
         error_msg = f"MongoDB Operation Failure (Auth/Permissions?): {of}"
         logging.error(error_msg)
         return None, error_msg
    except Exception as e:
        error_msg = f"An unexpected error occurred during MongoDB connection: {e}"
        logging.exception(error_msg) 
        return None, error_msg

def get_db() -> Tuple[Optional[Database], str]:
    """
    Gets the database instance, connecting if necessary.
    Returns the database instance and an error message.
    """
    global _db
    if _db is not None:
        return _db, ""

    client, error = _connect_to_db()
    if error or not client:
        return None, error

    try:
        _db = client[DATABASE_NAME]
        logging.info(f"Accessed database: {DATABASE_NAME}")
        return _db, ""
    except Exception as e:
        error_msg = f"Error accessing database '{DATABASE_NAME}': {e}"
        logging.exception(error_msg)
        return None, error_msg

class User(UserMixin):
    """Represents a user for Flask-Login."""
    def __init__(self, user_data: Dict[str, Any]):
        """
        Initialize User object from database data.

        Args:
            user_data: Dictionary fetched from the 'userinfo' collection.
                       Expected keys: '_id', 'username', 'email', 'password_hash'.
        """
        if not user_data:
            raise ValueError("Cannot initialize User with empty data.")

        # Store the essential data, ensuring _id is present
        self.id = str(user_data.get('_id')) # Store ID as string, required by Flask-Login
        self.username = user_data.get('username')
        self.email = user_data.get('email')
        self.password_hash = user_data.get('password_hash')
        # Add any other user fields you might need access to via current_user
        # self.created_at = user_data.get('created_at')

        # --- Important: Validate essential fields ---
        if not self.id or not self.username or not self.email or not self.password_hash:
             logging.error(f"User data missing essential fields during User object creation: {user_data}")
             # Decide how to handle this - raise error or create an invalid user?
             # Raising an error is safer during development.
             raise ValueError("User data from database is missing required fields (_id, username, email, password_hash).")


    # Flask-Login requires get_id() to return the user's unique ID as a string
    def get_id(self):
        return self.id

    def check_password(self, password_to_check: str) -> bool:
        """Verifies the provided password against the stored hash."""
        if not self.password_hash:
             logging.error(f"User {self.username} has no password hash stored.")
             return False
        return check_password_hash(self.password_hash, password_to_check)

def find_user_by_id(user_id: ObjectId) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Finds a single user record by their MongoDB ObjectId.

    Args:
        user_id: The ObjectId of the user.

    Returns:
        A tuple (user_document or None, error_message)
    """
    collection, error = get_userinfo_collection()
    if error or collection is None:
        logging.error(f"Failed to get userinfo collection for ID check: {error}")
        return None, f"Failed to get userinfo collection: {error}"

    if not isinstance(user_id, ObjectId):
        # Basic type check, ObjectId conversion happens in user_loader
        logging.error(f"Invalid type passed to find_user_by_id: {type(user_id)}")
        return None, "Invalid user ID format."

    try:
        user = collection.find_one({"_id": user_id})
        if user:
            logging.debug(f"Found user record for ID: {user_id}")
            return user, "" # Return the user document
        else:
            logging.debug(f"No user record found for ID: {user_id}")
            return None, "" # Not found isn't an error here

    except Exception as e:
        error_msg = f"Unexpected error finding user by ID '{user_id}': {e}"
        logging.exception(error_msg)
        return None, error_msg

def get_metadata_collection() -> Tuple[Optional[Collection], str]:
    """
    Gets the file_metadata collection instance, connecting if necessary.
    Returns the collection instance and an error message.
    """
    global _collection
    if _collection is not None:
        return _collection, ""

    db_instance, error = get_db()
    if error or db_instance is None:
        return None, error

    try:
        _collection = db_instance[COLLECTION_NAME]
        logging.info(f"Accessed collection: {COLLECTION_NAME}")
        return _collection, ""
    except Exception as e:
        error_msg = f"Error accessing collection '{COLLECTION_NAME}': {e}"
        logging.exception(error_msg)
        return None, error_msg

# --- Application Specific Database Functions ---
def save_file_metadata(record: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Saves a single file upload record (document) to the metadata collection.
    Overwrites existing record if one with the same 'access_id' exists (upsert).

    Args:
        record: A dictionary containing the metadata for one uploaded file.
                Must include an 'access_id' key.

    Returns:
        A tuple (success: bool, message: str)
    """
    collection, error = get_metadata_collection()
    if error or collection is None:
        return False, f"Failed to get collection: {error}"

    if "access_id" not in record:
        return False, "Record is missing 'access_id' field."

    try:
        
        result = collection.update_one(
            {"access_id": record["access_id"]}, 
            {"$set": record},                   
            upsert=True                         
        )
        if result.upserted_id:
            logging.info(f"Successfully inserted metadata for access_id: {record['access_id']}")
            return True, f"Metadata inserted (ID: {result.upserted_id})."
        elif result.modified_count > 0:
            logging.info(f"Successfully updated metadata for access_id: {record['access_id']}")
            return True, "Metadata updated."
        elif result.matched_count > 0:
             logging.info(f"Metadata for access_id {record['access_id']} already exists and is identical.")
             return True, "Metadata already up-to-date."
        else:
             logging.warning(f"Upsert for access_id {record['access_id']} neither inserted nor modified.")
             return False, "Upsert completed unexpectedly (no change)."


    except OperationFailure as of:
        error_msg = f"Database operation failed saving metadata: {of}"
        logging.exception(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Unexpected error saving metadata: {e}"
        logging.exception(error_msg)
        return False, error_msg

def find_metadata_by_username(username: str) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """
    Finds all metadata records for a given username.

    Args:
        username: The username to search for.

    Returns:
        A tuple (list_of_records or None, error_message)
    """
    collection, error = get_metadata_collection()
    if error or collection is None:
        return None, f"Failed to get collection: {error}"

    try:
        records_cursor = collection.find({"username": username})
        records_list = list(records_cursor) 
        logging.info(f"Found {len(records_list)} metadata records for username: {username}")
        return records_list, ""

    except OperationFailure as of:
        error_msg = f"Database operation failed finding metadata by username: {of}"
        logging.exception(error_msg)
        return None, error_msg
    except Exception as e:
        error_msg = f"Unexpected error finding metadata by username: {e}"
        logging.exception(error_msg)
        return None, error_msg

def find_metadata_by_access_id(access_id: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Finds a single metadata record by its unique access_id.

    Args:
        access_id: The unique access ID to search for.

    Returns:
        A tuple (record_dictionary or None, error_message)
    """
    collection, error = get_metadata_collection()
    if error or collection is None:
        return None, f"Failed to get collection: {error}"

    try:
        record = collection.find_one({"access_id": access_id})
        if record:
            logging.info(f"Found metadata record for access_id: {access_id}")
            return record, ""
        else:
            logging.info(f"No metadata record found for access_id: {access_id}")
            return None, "File record not found." 

    except OperationFailure as of:
        error_msg = f"Database operation failed finding metadata by access_id: {of}"
        logging.exception(error_msg)
        return None, error_msg
    except Exception as e:
        error_msg = f"Unexpected error finding metadata by access_id: {e}"
        logging.exception(error_msg)
        return None, error_msg

def delete_metadata_by_filename(username: str, original_filename: str) -> Tuple[int, str]:
    """
    Deletes metadata record(s) matching a username and original filename.
    Note: This could potentially delete multiple records if a user uploads
          files with the same name. Consider using access_id for unique deletion.

    Args:
        username: The username.
        original_filename: The original filename stored in the record.

    Returns:
        A tuple (number_of_deleted_records, error_message)
    """
    collection, error = get_metadata_collection()
    if error or collection is None:
        return 0, f"Failed to get collection: {error}"

    try:
        result = collection.delete_many({
            "username": username,
            "original_filename": original_filename
        })
        deleted_count = result.deleted_count
        if deleted_count > 0:
            logging.info(f"Deleted {deleted_count} metadata record(s) for user '{username}', filename '{original_filename}'.")
        else:
             logging.info(f"No metadata records found to delete for user '{username}', filename '{original_filename}'.")
        return deleted_count, ""

    except OperationFailure as of:
        error_msg = f"Database operation failed deleting metadata: {of}"
        logging.exception(error_msg)
        return 0, error_msg
    except Exception as e:
        error_msg = f"Unexpected error deleting metadata: {e}"
        logging.exception(error_msg)
        return 0, error_msg

def close_db_connection():
    """Closes the MongoDB client connection if it's open."""
    global _client
    if _client:
        try:
            _client.close()
            _client = None 
            logging.info("MongoDB connection closed.")
        except Exception as e:
            logging.error(f"Error closing MongoDB connection: {e}")

logging.info("Database module initialized.")



# --- User Information Collection Functions ---

_userinfo_collection: Optional[Collection] = None # Global variable for userinfo collection

def get_userinfo_collection() -> Tuple[Optional[Collection], str]:
    """
    Gets the userinfo collection instance, connecting if necessary.
    Returns the collection instance and an error message.
    """
    global _userinfo_collection # Allow modification of the global variable
    if _userinfo_collection is not None:
        return _userinfo_collection, ""

    db_instance, error = get_db() # Reuse existing DB connection function
    if error or db_instance is None:
        return None, error

    try:
        # Use the specific collection name for user info
        _userinfo_collection = db_instance["userinfo"]
        logging.info(f"Accessed collection: userinfo")
        return _userinfo_collection, ""
    except Exception as e:
        error_msg = f"Error accessing collection 'userinfo': {e}"
        logging.exception(error_msg)
        return None, error_msg

def find_user_by_email(email: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Finds a single user record by their email address.

    Args:
        email: The email address to search for.

    Returns:
        A tuple (user_document or None, error_message)
    """
    collection, error = get_userinfo_collection()
    if error or collection is None:
        return None, f"Failed to get userinfo collection: {error}"

    try:
        # Convert email to lowercase for case-insensitive check
        email_lower = email.lower()
        user = collection.find_one({"email": email_lower})
        if user:
            logging.info(f"Found user record for email: {email_lower}")
            return user, ""
        else:
            logging.info(f"No user record found for email: {email_lower}")
            return None, "" # Return None, but no error message if simply not found

    except OperationFailure as of:
        error_msg = f"Database operation failed finding user by email: {of}"
        logging.exception(error_msg)
        return None, error_msg
    except Exception as e:
        error_msg = f"Unexpected error finding user by email: {e}"
        logging.exception(error_msg)
        return None, error_msg

def save_user(user_data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Saves a new user document to the userinfo collection.
    Assumes email uniqueness has already been checked.

    Args:
        user_data: A dictionary containing the new user's data (including hashed password).

    Returns:
        A tuple (success: bool, message: str)
    """
    collection, error = get_userinfo_collection()
    if error or collection is None:
        return False, f"Failed to get userinfo collection: {error}"

    if "email" not in user_data or "password_hash" not in user_data:
        return False, "User data is missing required email or password_hash fields."

    try:
        # Convert email to lowercase before saving
        user_data["email"] = user_data["email"].lower()

        result = collection.insert_one(user_data)
        if result.inserted_id:
            logging.info(f"Successfully inserted new user with ID: {result.inserted_id}")
            return True, f"User created successfully (ID: {result.inserted_id})."
        else:
             logging.warning(f"User insert operation completed but reported no inserted ID.")
             return False, "User insert operation finished unexpectedly."

    except OperationFailure as of:
        # This might catch duplicate key errors if an index is set on email,
        # but we should ideally check find_user_by_email first.
        error_msg = f"Database operation failed saving user: {of}"
        logging.exception(error_msg)
        # Check if it's a duplicate key error (E11000)
        if "E11000" in str(of):
            return False, "Email address already exists."
        return False, error_msg
    except Exception as e:
        error_msg = f"Unexpected error saving user: {e}"
        logging.exception(error_msg)
        return False, error_msg
    
def find_user_by_username(username: str) -> Tuple[Optional[Dict[str, Any]], str]:
    # ... (keep the implementation from the previous step) ...
    """
    Finds a single user record by their username.

    Args:
        username: The username to search for (case-sensitive by default).

    Returns:
        A tuple (user_document or None, error_message)
    """
    collection, error = get_userinfo_collection() # Assumes you have this function
    if error or collection is None:
        logging.error(f"Failed to get userinfo collection for username check: {error}")
        return None, f"Failed to get userinfo collection: {error}"

    try:
        # Query the database for the username.
        user = collection.find_one({"username": username})

        if user:
            logging.info(f"Found user record for username: {username}")
            return user, "" # Return the user document and empty error string
        else:
            logging.info(f"No user record found for username: {username}")
            return None, "" # Return None (not found), but no error message

    except Exception as e:
        error_msg = f"Unexpected error finding user by username '{username}': {e}"
        logging.exception(error_msg) # Log the full traceback
        return None, error_msg # Return None and the error message
    
def find_metadata_by_email(user_email: str) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """
    Finds all file metadata records for a given user email.
    Args: user_email: The user's email address.
    Returns: A tuple (list_of_records or None, error_message)
    """
    collection, error = get_metadata_collection() # Use the 'user_files' collection
    if error or collection is None:
        return None, f"Failed to get metadata collection: {error}"

    try:
        # Ensure the query field 'user_email' matches what you save in the record
        records_cursor = collection.find({"user_email": user_email.lower()}) # Query by email
        records_list = list(records_cursor)
        logging.info(f"Found {len(records_list)} metadata records for email: {user_email}")
        return records_list, ""
    except Exception as e:
        error_msg = f"Unexpected error finding metadata by email '{user_email}': {e}"
        logging.exception(error_msg)
        return None, error_msg
    
def delete_metadata_by_access_id(access_id: str) -> Tuple[int, str]:
    """
    Deletes a single metadata record matching the unique access_id.
    Args: access_id: The unique access ID of the record to delete.
    Returns: A tuple (deleted_count (0 or 1), error_message)
    """
    collection, error = get_metadata_collection() # Use the 'user_files' collection
    if error or collection is None:
        return 0, f"Failed to get metadata collection: {error}"

    try:
        result = collection.delete_one({"access_id": access_id}) # Use delete_one for unique ID
        deleted_count = result.deleted_count
        if deleted_count == 1:
            logging.info(f"Deleted metadata record for access_id '{access_id}'.")
        elif deleted_count == 0:
             logging.warning(f"No metadata record found to delete for access_id '{access_id}'.")
        else:
            # Should not happen with delete_one
            logging.error(f"Unexpected result deleting by access_id '{access_id}': Count={deleted_count}")

        return deleted_count, ""
    except Exception as e:
        error_msg = f"Unexpected error deleting metadata by access_id '{access_id}': {e}"
        logging.exception(error_msg)
        return 0, error_msg