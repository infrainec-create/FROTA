from flask import Blueprint, flash, redirect, request, session, url_for
from werkzeug.security import generate_password_hash
from auth import login_required
from database import audit, get_db
from security import csrf_protect
from validators import ValidationError, secure_password

users_bp = Blueprint("users", __name__)


@users_bp.route("/admin/users/<int:user_id>/approve", methods=["POST"])
@login_required(role="admin")
@csrf_protect
def approve_user(user_id):
    db = get_db(); db.execute("UPDATE users SET status='Aprovado', role='driver' WHERE id=? AND status='Pendente'", (user_id,))
    audit(db, "approve", "user", user_id, user_id=session["user_id"]); db.commit(); flash("Conta aprovada como motorista.", "success")
    return redirect(url_for("index"))


@users_bp.route("/admin/users/<int:user_id>/change-password", methods=["POST"])
@login_required(role="admin")
@csrf_protect
def change_user_password(user_id):
    try:
        password = secure_password(request.form.get("new_password", "")); db = get_db()
        db.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(password), user_id))
        audit(db, "change_password", "user", user_id, user_id=session["user_id"]); db.commit(); flash("Senha alterada.", "success")
    except ValidationError: flash("Senha inválida: use ao menos 12 caracteres, com letras e números.", "error")
    return redirect(url_for("index"))


@users_bp.route("/admin/users/<int:user_id>/toggle-role", methods=["POST"])
@login_required(role="admin")
@csrf_protect
def toggle_user_role(user_id):
    db = get_db(); user = db.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
    admins = db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND status='Aprovado'").fetchone()[0]
    if user and not (user_id == session["user_id"] or (user["role"] == "admin" and admins <= 1)):
        new_role = "driver" if user["role"] == "admin" else "admin"; db.execute("UPDATE users SET role=? WHERE id=?", (new_role, user_id))
        audit(db, "change_role", "user", user_id, f"role={new_role}", session["user_id"]); db.commit(); flash("Perfil atualizado.", "success")
    else: flash("Não é permitido remover o último administrador ativo.", "error")
    return redirect(url_for("index"))


@users_bp.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required(role="admin")
@csrf_protect
def delete_user(user_id):
    if user_id != session["user_id"]:
        db = get_db(); db.execute("UPDATE users SET status='Bloqueado' WHERE id=?", (user_id,))
        audit(db, "block", "user", user_id, user_id=session["user_id"]); db.commit(); flash("Conta bloqueada; a auditoria foi preservada.", "success")
    return redirect(url_for("index"))
