from flask import Blueprint, render_template, request, session, redirect, url_for, flash, jsonify
from models.db import get_db
from utils.helpers import log_admin_action, add_notification
from datetime import datetime

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_email'):
        return redirect(url_for('marketplace.index'))
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET'])
def register():
    if session.get('user_email'):
        return redirect(url_for('marketplace.index'))
    return render_template('register.html')

@auth_bp.route('/forgot-password', methods=['GET'])
def forgot_password():
    return render_template('forgot_password.html')

@auth_bp.route('/api/auth/sync', methods=['POST'])
def sync_session():
    """Called from frontend after Firebase auth — syncs user into MongoDB and Flask session."""
    data = request.get_json()
    if not data or not data.get('email'):
        return jsonify({"error": "Invalid data"}), 400
    db = get_db()
    email = data['email'].lower().strip()
    user = db.users.find_one({"email": email})
    now = datetime.utcnow()
    if not user:
        db.users.insert_one({
            "email": email,
            "display_name": data.get('displayName', email.split('@')[0]),
            "photo_url": data.get('photoURL', ''),
            "firebase_uid": data.get('uid', ''),
            "role": "user",
            "active": True,
            "created_at": now,
            "last_login": now,
        })
        add_notification(db, email, "Welcome to CodeForge Market!", "Your account has been created successfully.", "success")
    else:
        db.users.update_one({"email": email}, {"$set": {"last_login": now, "firebase_uid": data.get('uid', '')}})
    user = db.users.find_one({"email": email})
    session.permanent = True
    session['user_email'] = email
    session['user_name'] = data.get('displayName', email.split('@')[0])
    session['user_photo'] = data.get('photoURL', '')
    session['user_role'] = user.get('role', 'user')
    return jsonify({"status": "ok", "redirect": url_for('user.dashboard')})

@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"status": "ok"})

@auth_bp.route('/logout')
def logout_page():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('marketplace.index'))
