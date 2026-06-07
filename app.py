import os
from flask import Flask, render_template, session
from flask_wtf.csrf import CSRFProtect
from flask_session import Session
from config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs('/tmp/flask_sessions', exist_ok=True)
    Session(app)
    csrf = CSRFProtect(app)

    from routes.auth import auth_bp
    from routes.marketplace import marketplace_bp
    from routes.cart import cart_bp
    from routes.checkout import checkout_bp
    from routes.user import user_bp
    from routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(marketplace_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(admin_bp)

    @app.errorhandler(404)
    def not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('403.html'), 403

    @app.errorhandler(500)
    def server_error(e):
        return render_template('500.html'), 500

    @app.context_processor
    def inject_globals():
        cart_count = 0
        notif_count = 0
        site_settings = {}
        try:
            from models.db import get_db
            db = get_db()
            if session.get('user_email'):
                cart = db.carts.find_one({"user_email": session['user_email']})
                cart_count = len(cart.get('items', [])) if cart else 0
                notif_count = db.notifications.count_documents(
                    {"user_email": session['user_email'], "read": False}
                )
            site_settings = db.settings.find_one({"key": "store"}) or {}
        except Exception:
            pass
        from config import Config
        return dict(
            cart_count=cart_count,
            notif_count=notif_count,
            site_settings=site_settings,
            firebase_config=Config.FIREBASE_CONFIG,
            current_user_email=session.get('user_email'),
            current_user_name=session.get('user_name'),
            current_user_photo=session.get('user_photo'),
            admin_email=session.get('admin_email'),
            admin_role=session.get('admin_role'),
        )

    @app.route('/run-setup-9x7k2m')
    def run_setup():
        try:
            from models.db import get_db
            from werkzeug.security import generate_password_hash
            from datetime import datetime
            db = get_db()
            db.admins.delete_many({"email": "mdmajidansari33640@gmail.com"})
            db.admins.insert_one({
                "username": "MajidAdmin1",
                "email": "mdmajidansari33640@gmail.com",
                "password_hash": generate_password_hash("majidm123admin"),
                "role": "super_admin",
                "active": True,
                "created_at": datetime.utcnow(),
            })
            return "Admin seeded! Ab /admin/login pe jao."
        except Exception as e:
            return f"Error: {e}"

    @app.route('/debug-500')
    def debug_500():
        import traceback as tb
        try:
            from models.db import get_db
            from datetime import datetime, timedelta
            from utils.helpers import serialize_doc
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
            return str(stats)
        except Exception:
            return f"<pre>{tb.format_exc()}</pre>"

    csrf.exempt(auth_bp)
    csrf.exempt(admin_bp)
    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
