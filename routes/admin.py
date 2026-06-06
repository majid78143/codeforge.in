from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from models.db import get_db
from utils.helpers import serialize_doc, log_admin_action, add_notification
from utils.decorators import admin_required, permission_required
from werkzeug.security import check_password_hash, generate_password_hash
from bson import ObjectId
from datetime import datetime, timedelta
import math

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_email'):
        return redirect(url_for('admin.dashboard'))
    if request.method == 'POST':
        data = request.get_json() or request.form.to_dict()
        email = data.get('email', '').lower().strip()
        password = data.get('password', '')
        db = get_db()
        admin = db.admins.find_one({"email": email, "active": True})
        if not admin or not check_password_hash(admin['password_hash'], password):
            if request.is_json:
                return jsonify({"error": "Invalid credentials"}), 401
            flash('Invalid credentials', 'danger')
            return render_template('admin/login.html')
        session.permanent = True
        session['admin_email'] = email
        session['admin_username'] = admin.get('username', email)
        session['admin_role'] = admin.get('role', 'support_manager')
        log_admin_action(db, email, "login", f"Admin logged in from IP {request.remote_addr}")
        if request.is_json:
            return jsonify({"status": "ok", "redirect": url_for('admin.dashboard')})
        return redirect(url_for('admin.dashboard'))
    return render_template('admin/login.html')

@admin_bp.route('/logout')
def admin_logout():
    if session.get('admin_email'):
        db = get_db()
        log_admin_action(db, session['admin_email'], "logout", "Admin logged out")
    session.pop('admin_email', None)
    session.pop('admin_username', None)
    session.pop('admin_role', None)
    return redirect(url_for('admin.admin_login'))

@admin_bp.route('/')
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    db = get_db()
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    stats = {
        "total_users": db.users.count_documents({}),
        "total_products": db.products.count_documents({"status": "active"}),
        "total_orders": db.orders.count_documents({"payment_status": "paid"}),
        "total_revenue": sum(o.get('total', 0) for o in db.orders.find({"payment_status": "paid"}, {"total": 1})),
        "month_orders": db.orders.count_documents({"payment_status": "paid", "paid_at": {"$gte": month_start}}),
        "month_revenue": sum(o.get('total', 0) for o in db.orders.find({"payment_status": "paid", "paid_at": {"$gte": month_start}}, {"total": 1})),
        "pending_reviews": db.reviews.count_documents({"approved": False}),
        "pending_custom_orders": db.custom_orders.count_documents({"status": "pending"}),
        "total_downloads": db.download_logs.count_documents({}),
    }
    recent_orders = list(db.orders.find({"payment_status": "paid"}).sort("paid_at", -1).limit(5))
    recent_users = list(db.users.find().sort("created_at", -1).limit(5))
    # Revenue last 7 days
    revenue_chart = []
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        day_rev = sum(o.get('total', 0) for o in db.orders.find({"payment_status": "paid", "paid_at": {"$gte": day_start, "$lt": day_end}}, {"total": 1}))
        revenue_chart.append({"date": day_start.strftime("%b %d"), "revenue": day_rev})
    return render_template('admin/dashboard.html', stats=stats,
        recent_orders=[serialize_doc(o) for o in recent_orders],
        recent_users=[serialize_doc(u) for u in recent_users],
        revenue_chart=revenue_chart)

# ── PRODUCTS ──────────────────────────────────────────────────────────────────
@admin_bp.route('/products')
@admin_required
@permission_required('manage_products')
def products():
    db = get_db()
    page = int(request.args.get('page', 1))
    per_page = 15
    q = request.args.get('q', '')
    query = {}
    if q:
        query['$text'] = {'$search': q}
    total = db.products.count_documents(query)
    prods = list(db.products.find(query).sort("created_at", -1).skip((page-1)*per_page).limit(per_page))
    cats = list(db.categories.find())
    return render_template('admin/products.html',
        products=[serialize_doc(p) for p in prods],
        categories=[serialize_doc(c) for c in cats],
        page=page, total=total, total_pages=math.ceil(total/per_page), q=q)

@admin_bp.route('/products/create', methods=['POST'])
@admin_required
@permission_required('manage_products')
def create_product():
    db = get_db()
    data = request.get_json() or request.form.to_dict()
    tags = data.get('tags', [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',') if t.strip()]
    gallery = data.get('gallery_images', [])
    if isinstance(gallery, str):
        gallery = [u.strip() for u in gallery.split('\n') if u.strip()]
    features = data.get('features', [])
    if isinstance(features, str):
        features = [f.strip() for f in features.split('\n') if f.strip()]
    product = {
        "title": data.get('title', '').strip(),
        "description": data.get('description', '').strip(),
        "price": float(data.get('price', 0)),
        "discount_price": float(data.get('discount_price', 0)) if data.get('discount_price') else None,
        "category": data.get('category', '').strip(),
        "tags": tags,
        "thumbnail_image_url": data.get('thumbnail_image_url', '').strip(),
        "banner_image_url": data.get('banner_image_url', '').strip(),
        "gallery_images": gallery,
        "features": features,
        "mediafire_download_link": data.get('mediafire_download_link', '').strip(),
        "status": data.get('status', 'active'),
        "sales_count": 0,
        "view_count": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    result = db.products.insert_one(product)
    log_admin_action(db, session['admin_email'], "create_product", f"Created: {product['title']}")
    return jsonify({"status": "ok", "id": str(result.inserted_id)})

@admin_bp.route('/products/<product_id>', methods=['GET'])
@admin_required
def get_product(product_id):
    db = get_db()
    try:
        p = db.products.find_one({"_id": ObjectId(product_id)})
    except Exception:
        return jsonify({"error": "Not found"}), 404
    return jsonify(serialize_doc(p))

@admin_bp.route('/products/<product_id>/update', methods=['POST'])
@admin_required
@permission_required('manage_products')
def update_product(product_id):
    db = get_db()
    data = request.get_json() or request.form.to_dict()
    tags = data.get('tags', [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',') if t.strip()]
    gallery = data.get('gallery_images', [])
    if isinstance(gallery, str):
        gallery = [u.strip() for u in gallery.split('\n') if u.strip()]
    features = data.get('features', [])
    if isinstance(features, str):
        features = [f.strip() for f in features.split('\n') if f.strip()]
    update = {
        "title": data.get('title', '').strip(),
        "description": data.get('description', '').strip(),
        "price": float(data.get('price', 0)),
        "discount_price": float(data.get('discount_price', 0)) if data.get('discount_price') else None,
        "category": data.get('category', '').strip(),
        "tags": tags,
        "thumbnail_image_url": data.get('thumbnail_image_url', '').strip(),
        "banner_image_url": data.get('banner_image_url', '').strip(),
        "gallery_images": gallery,
        "features": features,
        "mediafire_download_link": data.get('mediafire_download_link', '').strip(),
        "status": data.get('status', 'active'),
        "updated_at": datetime.utcnow(),
    }
    try:
        db.products.update_one({"_id": ObjectId(product_id)}, {"$set": update})
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400
    log_admin_action(db, session['admin_email'], "update_product", f"Updated product {product_id}")
    return jsonify({"status": "ok"})

@admin_bp.route('/products/<product_id>/delete', methods=['POST'])
@admin_required
@permission_required('manage_products')
def delete_product(product_id):
    db = get_db()
    try:
        db.products.delete_one({"_id": ObjectId(product_id)})
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400
    log_admin_action(db, session['admin_email'], "delete_product", f"Deleted product {product_id}")
    return jsonify({"status": "ok"})

# ── CATEGORIES ────────────────────────────────────────────────────────────────
@admin_bp.route('/categories', methods=['GET'])
@admin_required
def categories():
    db = get_db()
    cats = list(db.categories.find())
    return jsonify([serialize_doc(c) for c in cats])

@admin_bp.route('/categories/create', methods=['POST'])
@admin_required
@permission_required('manage_products')
def create_category():
    db = get_db()
    data = request.get_json()
    db.categories.insert_one({"name": data['name'], "slug": data.get('slug', data['name'].lower().replace(' ','-')), "active": True})
    return jsonify({"status": "ok"})

# ── ORDERS ────────────────────────────────────────────────────────────────────
@admin_bp.route('/orders')
@admin_required
@permission_required('manage_orders')
def orders():
    db = get_db()
    page = int(request.args.get('page', 1))
    per_page = 15
    status_filter = request.args.get('status', '')
    query = {}
    if status_filter:
        query['payment_status'] = status_filter
    total = db.orders.count_documents(query)
    order_list = list(db.orders.find(query).sort("created_at", -1).skip((page-1)*per_page).limit(per_page))
    return render_template('admin/orders.html',
        orders=[serialize_doc(o) for o in order_list],
        page=page, total=total, total_pages=math.ceil(total/per_page), status_filter=status_filter)

@admin_bp.route('/orders/<order_id>')
@admin_required
def order_detail(order_id):
    db = get_db()
    order = db.orders.find_one({"order_id": order_id})
    if not order:
        return render_template('404.html'), 404
    return render_template('admin/order_detail.html', order=serialize_doc(order))

# ── USERS ─────────────────────────────────────────────────────────────────────
@admin_bp.route('/users')
@admin_required
@permission_required('manage_users')
def users():
    db = get_db()
    page = int(request.args.get('page', 1))
    per_page = 15
    q = request.args.get('q', '')
    query = {}
    if q:
        query['$or'] = [{"email": {"$regex": q, "$options": "i"}}, {"display_name": {"$regex": q, "$options": "i"}}]
    total = db.users.count_documents(query)
    user_list = list(db.users.find(query).sort("created_at", -1).skip((page-1)*per_page).limit(per_page))
    return render_template('admin/users.html',
        users=[serialize_doc(u) for u in user_list],
        page=page, total=total, total_pages=math.ceil(total/per_page), q=q)

@admin_bp.route('/users/<email>/toggle', methods=['POST'])
@admin_required
@permission_required('manage_users')
def toggle_user(email):
    db = get_db()
    user = db.users.find_one({"email": email})
    if not user:
        return jsonify({"error": "Not found"}), 404
    new_status = not user.get('active', True)
    db.users.update_one({"email": email}, {"$set": {"active": new_status}})
    log_admin_action(db, session['admin_email'], "toggle_user", f"User {email} active={new_status}")
    return jsonify({"status": "ok", "active": new_status})

# ── COUPONS ───────────────────────────────────────────────────────────────────
@admin_bp.route('/coupons')
@admin_required
@permission_required('manage_coupons')
def coupons():
    db = get_db()
    coupon_list = list(db.coupons.find().sort("created_at", -1))
    return render_template('admin/coupons.html', coupons=[serialize_doc(c) for c in coupon_list])

@admin_bp.route('/coupons/create', methods=['POST'])
@admin_required
@permission_required('manage_coupons')
def create_coupon():
    db = get_db()
    data = request.get_json() or request.form.to_dict()
    code = data.get('coupon_code', '').strip().upper()
    if not code:
        return jsonify({"error": "Coupon code required"}), 400
    if db.coupons.count_documents({"coupon_code": code}):
        return jsonify({"error": "Coupon code already exists"}), 400
    expiry = None
    if data.get('expiry_date'):
        try:
            expiry = datetime.strptime(data['expiry_date'], '%Y-%m-%d')
        except Exception:
            pass
    db.coupons.insert_one({
        "coupon_code": code,
        "discount_type": data.get('discount_type', 'percentage'),
        "discount_value": float(data.get('discount_value', 10)),
        "expiry_date": expiry,
        "usage_limit": int(data.get('usage_limit', 0)),
        "per_user_limit": int(data.get('per_user_limit', 1)),
        "minimum_order_value": float(data.get('minimum_order_value', 0)),
        "active_status": data.get('active_status', True) in [True, 'true', '1', 'on'],
        "created_at": datetime.utcnow(),
    })
    log_admin_action(db, session['admin_email'], "create_coupon", f"Created coupon: {code}")
    return jsonify({"status": "ok"})

@admin_bp.route('/coupons/<coupon_id>/toggle', methods=['POST'])
@admin_required
@permission_required('manage_coupons')
def toggle_coupon(coupon_id):
    db = get_db()
    try:
        c = db.coupons.find_one({"_id": ObjectId(coupon_id)})
        db.coupons.update_one({"_id": ObjectId(coupon_id)}, {"$set": {"active_status": not c.get('active_status', True)}})
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400
    return jsonify({"status": "ok"})

@admin_bp.route('/coupons/<coupon_id>/delete', methods=['POST'])
@admin_required
@permission_required('manage_coupons')
def delete_coupon(coupon_id):
    db = get_db()
    try:
        db.coupons.delete_one({"_id": ObjectId(coupon_id)})
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400
    return jsonify({"status": "ok"})

# ── REVIEWS ───────────────────────────────────────────────────────────────────
@admin_bp.route('/reviews')
@admin_required
def reviews():
    db = get_db()
    status = request.args.get('status', 'pending')
    approved = status == 'approved'
    review_list = list(db.reviews.find({"approved": approved}).sort("created_at", -1))
    return render_template('admin/reviews.html', reviews=[serialize_doc(r) for r in review_list], status=status)

@admin_bp.route('/reviews/<review_id>/approve', methods=['POST'])
@admin_required
def approve_review(review_id):
    db = get_db()
    try:
        db.reviews.update_one({"_id": ObjectId(review_id)}, {"$set": {"approved": True}})
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400
    return jsonify({"status": "ok"})

@admin_bp.route('/reviews/<review_id>/delete', methods=['POST'])
@admin_required
def delete_review(review_id):
    db = get_db()
    try:
        db.reviews.delete_one({"_id": ObjectId(review_id)})
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400
    return jsonify({"status": "ok"})

# ── CUSTOM ORDERS ─────────────────────────────────────────────────────────────
@admin_bp.route('/custom-orders')
@admin_required
def custom_orders():
    db = get_db()
    status = request.args.get('status', 'pending')
    orders_list = list(db.custom_orders.find({"status": status}).sort("created_at", -1))
    return render_template('admin/custom_orders.html', orders=[serialize_doc(o) for o in orders_list], status=status)

@admin_bp.route('/custom-orders/<order_id>/action', methods=['POST'])
@admin_required
def custom_order_action(order_id):
    db = get_db()
    data = request.get_json()
    action = data.get('action')
    try:
        order = db.custom_orders.find_one({"_id": ObjectId(order_id)})
        if not ord6er:
            return jsonify({"error": "Not found"}), 404
        update = {"status": action, "updated_at": datetime.utcnow()}
        if action == 'quote_sent':
            update['quotation'] = data.get('quotation', '')
            update['quoted_amount'] = float(data.get('quoted_amount', 0))
        db.custom_orders.update_one({"_id": ObjectId(order_id)}, {"$set": update})
        msg_map = {
            "accepted": "Your custom development request has been accepted!",
            "rejected": "Your custom development request was rejected.",
            "quote_sent": f"You have a new quotation: ₹{data.get('quoted_amount', 0)} - {data.get('quotation', '')}",
        }
        if action in msg_map:
            add_notification(db, order['user_email'], f"Custom Order Update", msg_map[action], "info")
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"status": "ok"})

# ── ANALYTICS ─────────────────────────────────────────────────────────────────
@admin_bp.route('/analytics')
@admin_required
def analytics():
    db = get_db()
    now = datetime.utcnow()
    months = []
    for i in range(5, -1, -1):
        ms = (now.replace(day=1) - timedelta(days=i*30)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        me = (ms + timedelta(days=32)).replace(day=1)
        rev = sum(o.get('total', 0) for o in db.orders.find({"payment_status": "paid", "paid_at": {"$gte": ms, "$lt": me}}, {"total": 1}))
        cnt = db.orders.count_documents({"payment_status": "paid", "paid_at": {"$gte": ms, "$lt": me}})
        months.append({"label": ms.strftime("%b %Y"), "revenue": rev, "orders": cnt})
    top_products = list(db.products.find({"status": "active"}).sort("sales_count", -1).limit(10))
    coupon_stats = list(db.coupon_usage.aggregate([
        {"$group": {"_id": "$coupon_code", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}, {"$limit": 10}
    ]))
    download_stats = list(db.download_logs.aggregate([
        {"$group": {"_id": "$product_title", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}, {"$limit": 10}
    ]))
    return render_template('admin/analytics.html',
        months=months,
        top_products=[serialize_doc(p) for p in top_products],
        coupon_stats=coupon_stats,
        download_stats=download_stats)

# ── SETTINGS ──────────────────────────────────────────────────────────────────
@admin_bp.route('/settings')
@admin_required
@permission_required('manage_settings')
def settings():
    db = get_db()
    s = db.settings.find_one({"key": "store"}) or {}
    return render_template('admin/settings.html', settings=serialize_doc(s))

@admin_bp.route('/settings/update', methods=['POST'])
@admin_required
@permission_required('manage_settings')
def update_settings():
    db = get_db()
    data = request.get_json() or request.form.to_dict()
    allowed = [
        'site_name','site_tagline','contact_email','currency','tax_percent',
        'announcement','announcement_active','seo_title','seo_description','seo_keywords',
        'homepage_hero_title','homepage_hero_subtitle','homepage_hero_cta',
        'homepage_featured_limit','homepage_trending_limit',
        'razorpay_key_id','razorpay_key_secret'
    ]
    update = {k: data[k] for k in allowed if k in data}
    if 'tax_percent' in update:
        update['tax_percent'] = float(update['tax_percent'])
    if 'homepage_featured_limit' in update:
        update['homepage_featured_limit'] = int(update['homepage_featured_limit'])
    if 'homepage_trending_limit' in update:
        update['homepage_trending_limit'] = int(update['homepage_trending_limit'])
    if 'announcement_active' in update:
        update['announcement_active'] = update['announcement_active'] in [True,  '1', 'on']
    db.settings.update_one({"key": "store"}, {"$set": update})
    log_admin_action(db, session['admin_email'], "update_settings", "Store settings updated")
    return jsonify({"status": "ok"})

# ── ADMIN MANAGEMENT ──────────────────────────────────────────────────────────
@admin_bp.route('/admins')
@admin_required
@permission_required('manage_admins')
def admin_management():
    db = get_db()
    admins = list(db.admins.find())
    roles = list(db.admin_roles.find())
    return render_template('admin/admins.html',
        admins=[serialize_doc(a) for a in admins],
        roles=[serialize_doc(r) for r in roles])

@admin_bp.route('/admins/create', methods=['POST'])
@admin_required
@permission_required('manage_admins')
def create_admin():
    db = get_db()
    data = request.get_json()
    if db.admins.count_documents({"email": data['email']}):
        return jsonify({"error": "Email already exists"}), 400
    db.admins.insert_one({
        "username": data['username'],
        "email": data['email'].lower().strip(),
        "password_hash": generate_password_hash(data['password']),
        "role": data.get('role', 'support_manager'),
        "active": True,
        "created_at": datetime.utcnow(),
        "created_by": session['admin_email']
    })
    log_admin_action(db, session['admin_email'], "create_admin", f"Created admin: {data['email']}")
    return jsonify({"status": "ok"})

@admin_bp.route('/admins/<admin_id>/toggle', methods=['POST'])
@admin_required
@permission_required('manage_admins')
def toggle_admin(admin_id):
    db = get_db()
    try:
        a = db.admins.find_one({"_id": ObjectId(admin_id)})
        if a and a['email'] == session['admin_email']:
            return jsonify({"error": "Cannot deactivate yourself"}), 400
        db.admins.update_one({"_id": ObjectId(admin_id)}, {"$set": {"active": not a.get('active', True)}})
    except Exception:
        return jsonify({"error": "Invalid ID"}), 400
    return jsonify({"status": "ok"})

@admin_bp.route('/logs')
@admin_required
def admin_logs():
    db = get_db()
    page = int(request.args.get('page', 1))
    per_page = 20
    total = db.admin_logs.count_documents({})
    logs = list(db.admin_logs.find().sort("timestamp", -1).skip((page-1)*per_page).limit(per_page))
    return render_template('admin/logs.html',
        logs=[serialize_doc(l) for l in logs],
        page=page, total=total, total_pages=math.ceil(total/per_page))

@admin_bp.route('/notifications')
@admin_required
def admin_notifications():
    db = get_db()
    notifs = list(db.notifications.find({"user_email": "admin"}).sort("created_at", -1).limit(50))
    db.notifications.update_many({"user_email": "admin", "read": False}, {"$set": {"read": True}})
    return render_template('admin/notifications.html', notifications=[serialize_doc(n) for n in notifs])

@admin_bp.route('/notifications/send', methods=['POST'])
@admin_required
def send_notification():
    db = get_db()
    data = request.get_json()
    target = data.get('target', 'all')
    title = data.get('title', '')
    message = data.get('message', '')
    if target == 'all':
        users = list(db.users.find({}, {"email": 1}))
        for u in users:
            add_notification(db, u['email'], title, message, data.get('type', 'info'))
    else:
        add_notification(db, target, title, message, data.get('type', 'info'))
    return jsonify({"status": "ok"})
