from datetime import datetime
from bson import ObjectId
import json, re

def serialize_doc(doc):
    """Convert MongoDB document to JSON-serializable dict."""
    if doc is None:
        return None
    result = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        elif isinstance(v, list):
            result[k] = [serialize_doc(i) if isinstance(i, dict) else (str(i) if isinstance(i, ObjectId) else i) for i in v]
        elif isinstance(v, dict):
            result[k] = serialize_doc(v)
        else:
            result[k] = v
    return result

def paginate(cursor, page, per_page=12):
    total = cursor.count()
    items = list(cursor.skip((page - 1) * per_page).limit(per_page))
    total_pages = (total + per_page - 1) // per_page
    return {
        "items": [serialize_doc(i) for i in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
    }

def log_admin_action(db, admin_email, action, details=""):
    db.admin_logs.insert_one({
        "admin_email": admin_email,
        "action": action,
        "details": details,
        "timestamp": datetime.utcnow(),
    })

def add_notification(db, user_email, title, message, ntype="info"):
    db.notifications.insert_one({
        "user_email": user_email,
        "title": title,
        "message": message,
        "type": ntype,
        "read": False,
        "created_at": datetime.utcnow(),
    })

def format_currency(amount, currency="INR"):
    symbol = {"INR": "₹", "USD": "$", "EUR": "€"}.get(currency, "₹")
    return f"{symbol}{amount:,.2f}"

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text.strip('-')
  
