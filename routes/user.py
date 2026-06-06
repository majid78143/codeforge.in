from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from models.db import get_db
from utils.helpers import serialize_doc, add_notification
from utils.decorators import login_required, api_login_required
from bson import ObjectId
from datetime import datetime

user_bp = Blueprint('user', __name__)

@user_bp.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    email = session['user_email']
    orders = list(db.orders.find({"user_email": email, "payment_status": "paid"}).sort("paid_at", -1).limit(5))
    downloads = list(db.download_logs.find({"user_email": email}).sort("downloaded_at", -1).limit(5))
    wishlist_count = 0
    user = db.users.find_one({"email": email})
    if user:
        wishlist_count = len(user.get('wishlist', []))
    notif_count = db.notifications.count_documents({"user_email": email, "read": False})
    return render_template('dashboard.html',
        orders=[serialize_doc(o) for o in orders],
        downloads=[serialize_doc(d) for d in downloads],
        wishlist_count=wishlist_count,
        notif_count=notif_count
    )

@user_bp.route('/orders')
@login_required
def orders():
    db = get_db()
    page = int(request.args.get('page', 1))
    per_page = 10
    email = session['user_email']
    total = db.orders.count_documents({"user_email": email})
    order_list = list(db.orders.find({"user_email": email}).sort("created_at", -1).skip((page-1)*per_page).limit(per_page))
    import math
    return render_template('orders.html',
        orders=[serialize_doc(o) for o in order_list],
        page=page, total=total, total_pages=math.ceil(total/per_page)
    )

@user_bp.route('/downloads')
@login_required
def downloads():
    db = get_db()
    email = session['user_email']
    paid_orders = list(db.orders.find({"user_email": email, "payment_status": "paid"}))
    products_purchased = {}
    for order in paid_orders:
        for item in order.get('items', []):
            pid = item.get('_id') or item.get('product_id')
            if pid and pid not in products_purchased:
                products_purchased[pid] = item
    return render_template('downloads.html', products=list(products_purchased.values()),
                           orders=paid_orders)

@user_bp.route('/api/download/<product_id>')
@api_login_required
def download_product(product_id):
    db = get_db()
    email = session['user_email']
    paid = db.orders.count_documents({
        "user_email": email,
        "items._id": product_id,
        "payment_status": "paid"
    })
    if paid == 0:
        return jsonify({"error": "Purchase required to download"}), 403
    try:
        product = db.products.find_one({"_id": ObjectId(product_id)})
    except Exception:
        return jsonify({"error": "Invalid product"}), 400
    if not product or not product.get('mediafire_download_link'):
        return jsonify({"error": "Download link not available"}), 404
    db.download_logs.insert_one({
        "user_email": email,
        "product_id": product_id,
        "product_title": product.get('title'),
        "downloaded_at": datetime.utcnow()
    })
    return jsonify({"url": product['mediafire_download_link']})

@user_bp.route('/wishlist')
@login_required
def wishlist():
    db = get_db()
    user = db.users.find_one({"email": session['user_email']})
    wishlist_ids = user.get('wishlist', []) if user else []
    products = []
    for wid in wishlist_ids:
        try:
            p = db.products.find_one({"_id": ObjectId(wid), "status": "active"})
            if p:
                products.append(serialize_doc(p))
        except Exception:
            pass
    return render_template('wishlist.html', products=products)

@user_bp.route('/api/wishlist/toggle', methods=['POST'])
@api_login_required
def toggle_wishlist():
    db = get_db()
    data = request.get_json()
    product_id = data.get('product_id')
    if not product_id:
        return jsonify({"error": "Product ID required"}), 400
    user = db.users.find_one({"email": session['user_email']})
    wishlist = user.get('wishlist', []) if user else []
    if product_id in wishlist:
        wishlist.remove(product_id)
        action = 'removed'
    else:
        wishlist.append(product_id)
        action = 'added'
    db.users.update_one({"email": session['user_email']}, {"$set": {"wishlist": wishlist}})
    return jsonify({"status": "ok", "action": action, "count": len(wishlist)})

@user_bp.route('/notifications')
@login_required
def notifications():
    db = get_db()
    notifs = list(db.notifications.find({"user_email": session['user_email']}).sort("created_at", -1).limit(50))
    db.notifications.update_many({"user_email": session['user_email'], "read": False}, {"$set": {"read": True}})
    return render_template('notifications.html', notifications=[serialize_doc(n) for n in notifs])

@user_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    db = get_db()
    if request.method == 'POST':
        data = request.get_json() or request.form.to_dict()
        update = {}
        if data.get('display_name'):
            update['display_name'] = data['display_name']
        if data.get('phone'):
            update['phone'] = data['phone']
        if update:
            db.users.update_one({"email": session['user_email']}, {"$set": update})
        return jsonify({"status": "ok", "message": "Profile updated"})
    user = db.users.find_one({"email": session['user_email']})
    return render_template('profile.html', user=serialize_doc(user) if user else {})

@user_bp.route('/reviews')
@login_required
def my_reviews():
    db = get_db()
    reviews = list(db.reviews.find({"user_email": session['user_email']}).sort("created_at", -1))
    return render_template('reviews.html', reviews=[serialize_doc(r) for r in reviews])

@user_bp.route('/api/reviews/submit', methods=['POST'])
@api_login_required
def submit_review():
    db = get_db()
    data = request.get_json()
    product_id = data.get('product_id')
    rating = int(data.get('rating', 5))
    comment = data.get('comment', '').strip()
    if not product_id or not comment:
        return jsonify({"error": "Product and comment required"}), 400
    if rating < 1 or rating > 5:
        return jsonify({"error": "Rating must be 1-5"}), 400
    paid = db.orders.count_documents({
        "user_email": session['user_email'],
        "items._id": product_id,
        "payment_status": "paid"
    })
    existing = db.reviews.count_documents({"user_email": session['user_email'], "product_id": product_id})
    if existing:
        return jsonify({"error": "You have already reviewed this product"}), 400
    db.reviews.insert_one({
        "user_email": session['user_email'],
        "user_name": session.get('user_name', 'Anonymous'),
        "product_id": product_id,
        "rating": rating,
        "comment": comment,
        "approved": False,
        "created_at": datetime.utcnow()
    })
    return jsonify({"status": "ok", "message": "Review submitted for approval"})
      
