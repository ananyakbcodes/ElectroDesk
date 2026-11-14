from functools import wraps
from flask import session, redirect, url_for, flash


def login_required(view_func):
    """Redirect unauthenticated visitors to the login page (FR-35)."""
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access ElectroDesk.", "warning")
            return redirect(url_for("main.login"))
        return view_func(*args, **kwargs)
    return wrapped_view