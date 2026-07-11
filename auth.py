import time
import sqlite3
from collections import defaultdict, deque
from functools import wraps
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from database import audit, get_db
from security import csrf_protect
from validators import ValidationError, required, secure_password

auth_bp = Blueprint("auth", __name__)
_attempts = defaultdict(deque)


def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("auth.login"))
            if role and session.get("role") != role:
                return "Acesso negado: permissão insuficiente.", 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def _too_many_attempts(identifier):
    now = time.monotonic()
    attempts = _attempts[identifier]
    while attempts and now - attempts[0] > 15 * 60:
        attempts.popleft()
    return len(attempts) >= 5


@auth_bp.route("/login", methods=["GET", "POST"])
@csrf_protect
def login():
    if "user_id" in session:
        return redirect(url_for("index"))
    if request.method == "POST":
        identifier = f"{request.remote_addr}:{request.form.get('username', '').lower()}"
        if _too_many_attempts(identifier):
            flash("Muitas tentativas. Aguarde 15 minutos.", "error")
        else:
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if user and user["status"] == "Aprovado" and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"], session["username"], session["role"] = user["id"], user["username"], user["role"]
                audit(get_db(), "login", "user", user["id"], user_id=user["id"])
                get_db().commit()
                return redirect(url_for("index"))
            _attempts[identifier].append(time.monotonic())
            flash("Usuário, senha ou situação da conta inválidos.", "error")
    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required()
@csrf_protect
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
@csrf_protect
def register():
    if "user_id" in session:
        return redirect(url_for("index"))
    if request.method == "POST":
        try:
            username = required(request.form, "username", "Nome de usuário")
            if not username.replace("_", "").replace("-", "").isalnum() or not 3 <= len(username) <= 40:
                raise ValidationError("Use de 3 a 40 letras, números, hífen ou sublinhado no usuário.")
            password = secure_password(request.form.get("password", ""))
            db = get_db()
            db.execute("INSERT INTO users (username, password_hash, role, status) VALUES (?, ?, 'driver', 'Pendente')",
                       (username, generate_password_hash(password)))
            audit(db, "register", "user", details=f"username={username}")
            db.commit()
            flash("Solicitação enviada. Um administrador deverá aprová-la.", "success")
        except (ValidationError, sqlite3.IntegrityError):
            flash("Não foi possível criar a conta. Verifique os dados e tente outro usuário.", "error")
    return render_template("register.html")
