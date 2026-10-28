"""Account + emergency-contact routes — a small Flask blueprint kept separate
from app.py's travel-data routes.

Pages
-----
    GET/POST  /register   create an account
    GET/POST  /login      log in
    POST      /logout     log out
    GET/POST  /account    manage profile + emergency contacts

API (used by the SOS widget, static/js/sos.js)
---
    GET     /api/account/emergency-contacts        this user's saved contacts (empty + ok if logged out)
    POST    /api/account/emergency-contacts         add a contact
    DELETE  /api/account/emergency-contacts/<id>    remove a contact

Nothing here sends anything anywhere automatically — contacts are only ever
used client-side to pre-fill heyBro's own share/SMS/email composer, which
still requires the person to tap "send" themselves. See static/js/sos.js.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from web_app.extensions import db
from web_app.models import EmergencyContact, User

auth_bp = Blueprint("auth", __name__)


@auth_bp.get("/register")
def register_page():
    if current_user.is_authenticated:
        return redirect(url_for("auth.account_page"))
    return render_template("register.html", active="account")


@auth_bp.post("/register")
def register_submit():
    username = (request.form.get("username") or "").strip()
    email = (request.form.get("email") or "").strip() or None
    password = request.form.get("password") or ""
    confirm = request.form.get("confirm") or ""

    errors = []
    if len(username) < 3:
        errors.append("Username must be at least 3 characters.")
    if len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    if password != confirm:
        errors.append("Passwords don't match.")
    if username and User.query.filter_by(username=username).first():
        errors.append("That username is already taken.")
    if email and User.query.filter_by(email=email).first():
        errors.append("An account with that email already exists.")

    if errors:
        return render_template("register.html", active="account", errors=errors,
                                form={"username": username, "email": email}), 400

    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    login_user(user)
    return redirect(url_for("auth.account_page"))


@auth_bp.get("/login")
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("auth.account_page"))
    return render_template("login.html", active="account")


@auth_bp.post("/login")
def login_submit():
    identifier = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    user = User.query.filter((User.username == identifier) | (User.email == identifier)).first()
    if not user or not user.check_password(password):
        return render_template("login.html", active="account",
                                errors=["Incorrect username/email or password."],
                                form={"username": identifier}), 401
    login_user(user, remember=True)
    next_url = request.args.get("next")
    return redirect(next_url or url_for("auth.account_page"))


@auth_bp.post("/logout")
def logout_submit():
    logout_user()
    return redirect(url_for("index"))


@auth_bp.get("/account")
@login_required
def account_page():
    return render_template("account.html", active="account", contacts=current_user.emergency_contacts)


@auth_bp.post("/account")
@login_required
def account_update():
    email = (request.form.get("email") or "").strip() or None
    home_cc = (request.form.get("home_country_code") or "").strip().upper()[:2] or None
    current_user.email = email
    current_user.home_country_code = home_cc
    db.session.commit()
    return redirect(url_for("auth.account_page"))


@auth_bp.post("/account/contacts")
@login_required
def account_add_contact():
    name = (request.form.get("name") or "").strip()
    if not name:
        return redirect(url_for("auth.account_page"))
    contact = EmergencyContact(
        user_id=current_user.id, name=name,
        relation=(request.form.get("relation") or "").strip() or None,
        phone=(request.form.get("phone") or "").strip() or None,
        email=(request.form.get("email") or "").strip() or None,
        is_primary=not current_user.emergency_contacts,  # first contact added becomes primary by default
    )
    db.session.add(contact)
    db.session.commit()
    return redirect(url_for("auth.account_page"))


@auth_bp.post("/account/contacts/<int:contact_id>/delete")
@login_required
def account_delete_contact(contact_id):
    contact = EmergencyContact.query.filter_by(id=contact_id, user_id=current_user.id).first()
    if contact:
        db.session.delete(contact)
        db.session.commit()
    return redirect(url_for("auth.account_page"))


@auth_bp.post("/account/contacts/<int:contact_id>/make-primary")
@login_required
def account_make_primary(contact_id):
    for contact in current_user.emergency_contacts:
        contact.is_primary = (contact.id == contact_id)
    db.session.commit()
    return redirect(url_for("auth.account_page"))


# --- JSON API for the SOS widget --------------------------------------------

@auth_bp.get("/api/account/emergency-contacts")
def api_emergency_contacts():
    if not current_user.is_authenticated:
        return jsonify({"ok": True, "logged_in": False, "contacts": []})
    return jsonify({
        "ok": True, "logged_in": True,
        "contacts": [c.to_dict() for c in current_user.emergency_contacts],
    })
