from flask import Blueprint, render_template, request, jsonify, session
from models.db import get_db
from utils.helpers import serialize_doc
from utils.decorators import api_login_required, login_required
from bson import ObjectId
from datetime import datetime

cart_bp = Blueprint('cart', __name__)

def _get_or_create_cart(db, email):
    cart = db.carts.find_one({"user_email": email})
    if not cart:
        db.carts.insert_one({"user_email": email, "items": [], "updated_at": datetime.utcnow()})
        cart = db.carts.find_one({"user_email": email})
    return cart

@cart_bp.route('/cart')
@login_required
def cart():
    db = get_db()
    cart = _get_or_create_cart(db, session['user_email'])
    items_detail = []
    for item in cart.get('items', []):
        try:
            prod = db.products.find_one({"_id": ObjectId(item['product_id']), "status": "active"})
        except Exception:
            continue
        if prod:
            p = serialize_doc(prod)
            p['quantity'] = item.get('quantity', 1)
            items_detail.append(p)
    subtotal = sum((float(i.get('discount_price') or i.get('price', 0))) * i['quantity'] for i in items_detail)
    return render_template('cart.html', items=items_detail, subtotal=subtotal)

@cart_bp.route('/api/cart/add', methods=['POST'])
@api_login_required
def add_to_cart():
    db = get_db()
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = int(data.get('quantity', 1))
    if not product_id:
        return jsonify({"error": "Product ID required"}), 400
    try:
        prod = db.products.find_one({"_id": ObjectId(product_id), "status": "active"})
    except Exception:
        return jsonify({"error": "Invalid product"}), 400
    if not prod:
        return jsonify({"error": "Product not found"}), 404
    cart = _get_or_create_cart(db, session['user_email'])
    items = cart.get('items', [])
    for item in items:
        if item['product_id'] == product_id:
            item['quantity'] = item.get('quantity', 1) + quantity
            db.carts.update_one({"user_email": session['user_email']}, {"$set": {"items": items, "updated_at": datetime.utcnow()}})
            return jsonify({"status": "ok", "message": "Cart updated", "count": len(items)})
    items.append({"product_id": product_id, "quantity": quantity})
    db.carts.update_one({"user_email": session['user_email']}, {"$set": {"items": items, "updated_at": datetime.utcnow()}})
    return jsonify({"status": "ok", "message": "Added to cart", "count": len(items)})

@cart_bp.route('/api/cart/remove', methods=['POST'])
@api_login_required
def remove_from_cart():
    db = get_db()
    data = request.get_json()
    product_id = data.get('product_id')
    cart = _get_or_create_cart(db, session['user_email'])
    items = [i for i in cart.get('items', []) if i['product_id'] != product_id]
    db.carts.update_one({"user_email": session['user_email']}, {"$set": {"items": items, "updated_at": datetime.utcnow()}})
    return jsonify({"status": "ok", "count": len(items)})

@cart_bp.route('/api/cart/update', methods=['POST'])
@api_login_required
def update_cart():
    db = get_db()
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = int(data.get('quantity', 1))
    if quantity < 1:
        return jsonify({"error": "Quantity must be >= 1"}), 400
    cart = _get_or_create_cart(db, session['user_email'])
    items = cart.get('items', [])
    for item in items:
        if item['product_id'] == product_id:
            item['quantity'] = quantity
            break
    db.carts.update_one({"user_email": session['user_email']}, {"$set": {"items": items, "updated_at": datetime.utcnow()}})
    return jsonify({"status": "ok"})

@cart_bp.route('/api/cart/count')
def cart_count():
    if not session.get('user_email'):
        return jsonify({"count": 0})
    db = get_db()
    cart = db.carts.find_one({"user_email": session['user_email']})
    count = len(cart.get('items', [])) if cart else 0
    return jsonify({"count": count})
  
