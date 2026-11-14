from functools import wraps
from flask import Blueprint, jsonify, request, session, current_app
from services import inventory_service, billing_service, report_service

api_bp = Blueprint("api", __name__, url_prefix="/api")


def api_auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        provided_key = request.headers.get("X-API-Key", "")
        valid_key = current_app.config.get("INTERNAL_API_KEY", "")
        if "user_id" in session or (provided_key and provided_key == valid_key):
            return fn(*args, **kwargs)
        return jsonify({"error": "Unauthorized. Provide active session or valid X-API-Key header."}), 401
    return wrapper


@api_bp.route("/products", methods=["GET"])
@api_auth_required
def api_products():
    search = request.args.get("search", "")
    items = inventory_service.list_products(search=search, active_only=True, db_path=current_app.config["DB_PATH"])
    return jsonify({"count": len(items), "products": items})


@api_bp.route("/products/<int:product_id>", methods=["GET"])
@api_auth_required
def api_product_detail(product_id):
    prod = inventory_service.get_product_by_id(product_id, db_path=current_app.config["DB_PATH"])
    if not prod:
        return jsonify({"error": "Product not found"}), 404
    return jsonify(prod)


@api_bp.route("/sales", methods=["GET"])
@api_auth_required
def api_sales():
    sales = billing_service.list_sales(limit=50, db_path=current_app.config["DB_PATH"])
    return jsonify({"count": len(sales), "sales": sales})


@api_bp.route("/summary", methods=["GET"])
@api_auth_required
def api_summary():
    summary = report_service.get_dashboard_summary(db_path=current_app.config["DB_PATH"])
    return jsonify(summary)