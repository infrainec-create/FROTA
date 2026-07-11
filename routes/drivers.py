import sqlite3
from flask import Blueprint, flash, redirect, request, session, url_for
from auth import login_required
from database import audit, get_db
from security import csrf_protect
from validators import VALID_DRIVER_STATUS, ValidationError, normalized_cpf, required, valid_date

drivers_bp = Blueprint("drivers", __name__)


def _values():
    status = request.form.get("status")
    expiry = valid_date(request.form, "license_expiry", "Vencimento da CNH")
    if status not in VALID_DRIVER_STATUS:
        raise ValidationError("Status de motorista inválido.")
    return (required(request.form, "name", "Nome"), normalized_cpf(required(request.form, "cpf", "CPF")),
            required(request.form, "phone", "Telefone"), required(request.form, "license", "CNH"), status, expiry.isoformat())


@drivers_bp.route("/drivers", methods=["POST"])
@login_required(role="admin")
@csrf_protect
def create_driver():
    try:
        values = _values(); db = get_db()
        cursor = db.execute("INSERT INTO drivers (name, cpf, phone, license, status, license_expiry) VALUES (?, ?, ?, ?, ?, ?)", values)
        audit(db, "create", "driver", cursor.lastrowid, user_id=session["user_id"]); db.commit()
        flash("Motorista cadastrado.", "success")
    except (ValidationError, sqlite3.IntegrityError):
        flash("Não foi possível cadastrar o motorista. Verifique CPF e dados.", "error")
    return redirect(url_for("index"))


@drivers_bp.route("/drivers/<int:driver_id>", methods=["POST"])
@login_required(role="admin")
@csrf_protect
def update_driver(driver_id):
    try:
        db = get_db(); db.execute("UPDATE drivers SET name=?, cpf=?, phone=?, license=?, status=?, license_expiry=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (*_values(), driver_id))
        audit(db, "update", "driver", driver_id, user_id=session["user_id"]); db.commit(); flash("Motorista atualizado.", "success")
    except (ValidationError, sqlite3.IntegrityError):
        flash("Não foi possível atualizar o motorista.", "error")
    return redirect(url_for("index"))


@drivers_bp.route("/drivers/<int:driver_id>/delete", methods=["POST"])
@login_required(role="admin")
@csrf_protect
def delete_driver(driver_id):
    db = get_db()
    if db.execute("SELECT 1 FROM checkins WHERE driver_id=? AND checkout_at IS NULL", (driver_id,)).fetchone():
        flash("Não é possível inativar motorista em uso.", "error")
    else:
        db.execute("UPDATE drivers SET status='Inativo', updated_at=CURRENT_TIMESTAMP WHERE id=?", (driver_id,))
        audit(db, "deactivate", "driver", driver_id, user_id=session["user_id"]); db.commit(); flash("Motorista inativado; o histórico foi preservado.", "success")
    return redirect(url_for("index"))
