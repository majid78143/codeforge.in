import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'codeforge-secret-key-2024-xK9mP2nQ')
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = '/tmp/flask_sessions'

    # MongoDB
    MONGO_URI = "mongodb+srv://THEMAJID:THEBHUWAN@themajid.iuidi4z.mongodb.net/?appName=THEMAJID"
    MONGO_DB_NAME = "codeforge_market"

    # Razorpay (editable from admin panel — defaults shown here)
    RAZORPAY_KEY_ID = "rzp_live_TCTb1rwwA8rghn"
    RAZORPAY_KEY_SECRET = "pq9Sjdq9XFskgcfz5bLqKVoD"

    # Firebase (frontend only — kept here for template injection)
    FIREBASE_CONFIG = {
        "apiKey": "AIzaSyD3ML9k7RSbeoVze0su8PoE69llfgeqr1k",
        "authDomain": "codeforge-d3aa2.firebaseapp.com",
        "databaseURL": "https://codeforge-d3aa2-default-rtdb.firebaseio.com",
        "projectId": "codeforge-d3aa2",
        "storageBucket": "codeforge-d3aa2.firebasestorage.app",
        "messagingSenderId": "907268826856",
        "appId": "1:907268826856:web:aedb8eb1c674bad9ab4b5d",
        "measurementId": "G-BYDW3TQVV7"
    }

    # Super Admin seed
    SUPER_ADMIN = {
        "username": "MajidAdmin1",
        "email": "mdmajidansari33640@gmail.com",
        "raw_password": "majidm123admin"
    }
  
