from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure
from werkzeug.security import generate_password_hash
from datetime import datetime
import os

_client = None
_db = None

def get_db():
    global _client, _db
    if _db is None:
        from config import Config
        _client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=10000)
        _db = _client[Config.MONGO_DB_NAME]
        _ensure_collections(_db)
        _seed_super_admin(_db)
    return _db

def _ensure_collections(db):
    existing = db.list_collection_names()
    required = [
        "users","products","categories","orders","payments","coupons",
        "coupon_usage","reviews","custom_orders","settings","notifications",
        "download_logs","analytics","admins","admin_roles","admin_permissions","admin_logs"
    ]
    for col in required:
        if col not in existing:
            db.create_collection(col)
    # Indexes
    db.users.create_index([("email", ASCENDING)], unique=True, background=True)
    db.products.create_index([("title", "text"), ("description", "text")], background=True)
    db.products.create_index([("category", ASCENDING), ("status", ASCENDING)], background=True)
    db.orders.create_index([("user_email", ASCENDING)], background=True)
    db.coupons.create_index([("coupon_code", ASCENDING)], unique=True, background=True)
    db.admins.create_index([("email", ASCENDING)], unique=True, background=True)
    # Default settings
    if db.settings.count_documents({}) == 0:
        db.settings.insert_one({
            "key": "store",
            "site_name": "CodeForge Market",
            "site_tagline": "Premium Discord Bots & Automation Tools",
            "contact_email": "support@codeforgemarket.com",
            "razorpay_key_id": "",
            "razorpay_key_secret": "",
            "currency": "INR",
            "tax_percent": 0,
            "announcement": "",
            "announcement_active": False,
            "seo_title": "CodeForge Market - Premium Discord Bots",
            "seo_description": "Buy premium Discord bots, automation scripts, APIs and tools",
            "seo_keywords": "discord bot, automation, scripts, api, tools",
            "homepage_hero_title": "Premium Discord Bots & Automation Tools",
            "homepage_hero_subtitle": "Professional-grade bots, scripts, and tools for Discord servers",
            "homepage_hero_cta": "Browse Marketplace",
            "homepage_featured_limit": 6,
            "homepage_trending_limit": 4,
        })
    # Default admin roles
    if db.admin_roles.count_documents({}) == 0:
        roles = [
            {"role": "super_admin", "label": "Super Admin", "permissions": ["all"]},
            {"role": "product_manager", "label": "Product Manager", "permissions": ["manage_products"]},
            {"role": "order_manager", "label": "Order Manager", "permissions": ["manage_orders"]},
            {"role": "support_manager", "label": "Support Manager", "permissions": ["manage_users","manage_coupons"]},
        ]
        db.admin_roles.insert_many(roles)

def _seed_super_admin(db):
    from config import Config
    sa = Config.SUPER_ADMIN
    if db.admins.count_documents({"email": sa["email"]}) == 0:
        db.admins.insert_one({
            "username": sa["username"],
            "email": sa["email"],
            "password_hash": generate_password_hash(sa["raw_password"]),
            "role": "super_admin",
            "active": True,
            "created_at": datetime.utcnow(),
        })
      
