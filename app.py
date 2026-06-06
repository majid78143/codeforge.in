import os
from flask import Flask, render_template, session
from flask_wtf.csrf import CSRFProtect
from config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs('/tmp/flask_sessions', exist_ok=True)

    csrf = CSRFProtect(app)

    # Register blueprints
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

    # Initialize DB on startup
    with app.app_context():
        from models.db import get_db
        get_db()

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
        from models.db import get_db
        db = get_db()
        cart_count = 0
        notif_count = 0
        if session.get('user_email'):
            cart = db.carts.find_one({"user_email": session['user_email']})
            cart_count = len(cart.get('items', [])) if cart else 0
            notif_count = db.notifications.count_documents({"user_email": session['user_email'], "read": False})
        settings = db.settings.find_one({"key": "store"}) or {}
        from config import Config
        return dict(
            cart_count=cart_count,
            notif_count=notif_count,
            site_settings=settings,
            firebase_config=Config.FIREBASE_CONFIG,
            current_user_email=session.get('user_email'),
            current_user_name=session.get('user_name'),
            current_user_photo=session.get('user_photo'),
            admin_email=session.get('admin_email'),
            admin_role=session.get('admin_role'),
        )

    # CSRF exempt for Firebase auth sync
    csrf.exempt(auth_bp)

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
  
