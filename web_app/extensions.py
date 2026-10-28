"""Shared Flask extension instances — kept in their own module (not app.py) so
models.py and auth.py can import `db` / `login_manager` without circular imports.
"""
from __future__ import annotations

from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login_page"
login_manager.login_message = "Log in to view that page."
login_manager.login_message_category = "info"
