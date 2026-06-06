from flask import Blueprint, render_template, request, jsonify, session
from models.db import get_db
from utils.helpers import serialize_doc
from bson import ObjectId
import math

marketplace_bp = Blueprint('marketplace', __name__)

@marketplace_bp.route('/')
def index():
    db = get_db()
    settings = db.settings.find_one({"key": "store"}) or {}
    featured = list(db.products.find({"status": "active", "tags": "featured"}).limit(settings.get('homepage_featured_limit', 6)))
    trending = list(db.products.find({"status": "active", "tags": "trending"}).limit(settings.get('homepage_trending_limit', 4)))
    new_arrivals = list(db.products.find({"status": "active"}).sort("created_at", -1).limit(4))
    categories = list(db.categories.find({"active": True}))
    return render_template('index.html',
        featured=[serialize_doc(p) for p in featured],
        trending=[serialize_doc(p) for p in trending],
        new_arrivals=[serialize_doc(p) for p in new_arrivals],
        categories=[serialize_doc(c) for c in categories],
        settings=serialize_doc(settings)
    )

@marketplace_bp.route('/marketplace')
def marketplace():
    db = get_db()
    page = int(request.args.get('page', 1))
    per_page = 12
    category = request.args.get('category', '')
    tag = request.args.get('tag', '')
    sort = request.args.get('sort', 'latest')
    min_price = request.args.get('min_price', '')
    max_price = request.args.get('max_price', '')
    query = {"status": "active"}
    if category:
        query["category"] = category
    if tag:
        query["tags"] = tag
    if min_price or max_price:
        price_q = {}
        if min_price:
            price_q["$gte"] = float(min_price)
        if max_price:
            price_q["$lte"] = float(max_price)
        query["$or"] = [{"discount_price": price_q}, {"price": price_q}]
    sort_map = {
        "latest": [("created_at", -1)],
        "popular": [("sales_count", -1)],
        "price_asc": [("price", 1)],
        "price_desc": [("price", -1)],
    }
    sort_order = sort_map.get(sort, [("created_at", -1)])
    total = db.products.count_documents(query)
    products = list(db.products.find(query).sort(sort_order).skip((page-1)*per_page).limit(per_page))
    categories = list(db.categories.find({"active": True}))
    total_pages = math.ceil(total / per_page)
    return render_template('marketplace.html',
        products=[serialize_doc(p) for p in products],
        categories=[serialize_doc(c) for c in categories],
        page=page, total=total, total_pages=total_pages,
        current_category=category, current_tag=tag, current_sort=sort,
        per_page=per_page
    )

@marketplace_bp.route('/product/<product_id>')
def product_detail(product_id):
    db = get_db()
    try:
        product = db.products.find_one({"_id": ObjectId(product_id), "status": "active"})
    except Exception:
        return render_template('404.html'), 404
    if not product:
        return render_template('404.html'), 404
    reviews = list(db.reviews.find({"product_id": product_id, "approved": True}).sort("created_at", -1).limit(10))
    avg_rating = 0
    if reviews:
        avg_rating = sum(r.get('rating', 0) for r in reviews) / len(reviews)
    related = list(db.products.find({
        "status": "active",
        "category": product.get('category'),
        "_id": {"$ne": product['_id']}
    }).limit(4))
    db.products.update_one({"_id": product['_id']}, {"$inc": {"view_count": 1}})
    # Check if user has purchased
    purchased = False
    if session.get('user_email'):
        purchased = db.orders.count_documents({
            "user_email": session['user_email'],
            "items.product_id": product_id,
            "payment_status": "paid"
        }) > 0
    in_wishlist = False
    if session.get('user_email'):
        in_wishlist = db.users.count_documents({
            "email": session['user_email'],
            "wishlist": product_id
        }) > 0
    return render_template('product_detail.html',
        product=serialize_doc(product),
        reviews=[serialize_doc(r) for r in reviews],
        avg_rating=round(avg_rating, 1),
        related=[serialize_doc(p) for p in related],
        purchased=purchased,
        in_wishlist=in_wishlist
    )

@marketplace_bp.route('/api/search')
def live_search():
    db = get_db()
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({"results": []})
    results = list(db.products.find(
        {"status": "active", "$text": {"$search": q}},
        {"title": 1, "price": 1, "discount_price": 1, "thumbnail_image_url": 1, "category": 1}
    ).limit(8))
    return jsonify({"results": [serialize_doc(r) for r in results]})

@marketplace_bp.route('/about')
def about():
    return render_template('about.html')

@marketplace_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        db = get_db()
        db.notifications.insert_one({
            "user_email": "admin",
            "title": f"Contact from {request.form.get('name')}",
            "message": request.form.get('message'),
            "type": "contact",
            "email": request.form.get('email'),
            "read": False,
            "created_at": __import__('datetime').datetime.utcnow()
        })
        return jsonify({"status": "ok", "message": "Message sent successfully!"})
    return render_template('contact.html')

@marketplace_bp.route('/faq')
def faq():
    return render_template('faq.html')

@marketplace_bp.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy.html')

@marketplace_bp.route('/terms-and-conditions')
def terms():
    return render_template('terms.html')

@marketplace_bp.route('/refund-policy')
def refund_policy():
    return render_template('refund.html')

@marketplace_bp.route('/digital-delivery-policy')
def digital_delivery():
    return render_template('digital_delivery.html')

@marketplace_bp.route('/license-agreement')
def license():
    return render_template('license.html')

@marketplace_bp.route('/support-policy')
def support_policy():
    return render_template('support_policy.html')

@marketplace_bp.route('/custom-development', methods=['GET', 'POST'])
def custom_development():
    if request.method == 'POST':
        from utils.decorators import login_required
        if not session.get('user_email'):
            return jsonify({"error": "Login required"}), 401
        db = get_db()
        data = request.get_json() or request.form.to_dict()
        db.custom_orders.insert_one({
            "user_email": session['user_email'],
            "discord_username": data.get('discord_username'),
            "project_name": data.get('project_name'),
            "bot_type": data.get('bot_type'),
            "required_features": data.get('required_features'),
            "budget": data.get('budget'),
            "delivery_time": data.get('delivery_time'),
            "reference_links": data.get('reference_links', ''),
            "status": "pending",
            "created_at": __import__('datetime').datetime.utcnow(),
        })
        return jsonify({"status": "ok", "message": "Your request has been submitted!"})
    return render_template('custom_dev.html')
  
