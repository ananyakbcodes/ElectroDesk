from flask import Flask
from config import Config
from database.db import init_db
from services import auth_service, backup_service
from routes.main_routes import main_bp
from routes.product_routes import product_bp
from routes.sales_routes import sales_bp
from routes.purchase_routes import purchase_bp
from routes.ops_routes import ops_bp
from routes.api_routes import api_bp


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    # Ensure database schema and default admin/settings exist
    init_db(db_path=app.config["DB_PATH"])

    # Run automatic daily backup when not running isolated unit tests
    if not app.config.get("TESTING"):
        backup_service.run_daily_auto_backup(
            db_path=app.config["DB_PATH"],
            backup_dir=app.config["BACKUP_DIR"],
        )

    @app.context_processor
    def inject_store_settings():
        return {"store": auth_service.get_store_settings(db_path=app.config["DB_PATH"])}

    app.register_blueprint(main_bp)
    app.register_blueprint(product_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(purchase_bp)
    app.register_blueprint(ops_bp)
    app.register_blueprint(api_bp)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)