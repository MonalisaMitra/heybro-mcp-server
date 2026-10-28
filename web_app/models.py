"""Account storage — a user's own login plus the emergency-contact details
the SOS feature sends a location/photo link to.

This is a small, self-hosted store (SQLite by default — see app.py for the
DATABASE_URL override), not a replacement for a real identity provider: it
exists so a returning visitor doesn't have to re-type their emergency
contact every time. Passwords are hashed with werkzeug's PBKDF2 helper
(generate_password_hash/check_password_hash) — heyBro never stores or
displays a plaintext password anywhere, including to the account owner.
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from web_app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    home_country_code = db.Column(db.String(2), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    emergency_contacts = db.relationship(
        "EmergencyContact", backref="user", cascade="all, delete-orphan",
        order_by="EmergencyContact.is_primary.desc()",
    )

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    def to_public_dict(self) -> dict:
        return {
            "id": self.id, "username": self.username, "email": self.email,
            "home_country_code": self.home_country_code,
        }


class EmergencyContact(db.Model):
    __tablename__ = "emergency_contacts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    relation = db.Column(db.String(60), nullable=True)
    phone = db.Column(db.String(40), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    is_primary = db.Column(db.Boolean, default=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "relation": self.relation,
            "phone": self.phone, "email": self.email, "is_primary": bool(self.is_primary),
        }
