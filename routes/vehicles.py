import sqlite3
from datetime import date
from flask import Blueprint, flash, redirect, request, session, url_for
from auth import login_required
from database import audit, get_db
from security import csrf_protect
from validators import VALID_VEHICLE_STATUS, ValidationError, normalized_plate, required

vehicles_bp = Blueprint("vehicles", __name__)


@vehicles_bp.route("/vehicles", methods=["POST"])
@login_required(role="admin")
@csrf_protect
def create_vehicle():
    try:
        name = required(request.form, "name", "Nome")
        plate = normalized_plate(required(request.form, "plate", "Placa"))
        year = int(required(request.form, "year", "Ano"))
        status = request.form.get("status", "Disponível")
        if not 1900 <= year <= date.today().year + 1 or status not in VALID_VEHICLE_STATUS:
            raise ValidationError("Dados do veículo inválidos.")
        db = get_db()
        cursor = db.execute("INSERT INTO vehicles (name, plate, year, status) VALUES (?, ?, ?, ?)", (name, plate, year, status))
        audit(db, "create", "vehicle", cursor.lastrowid, f"plate={plate}", session["user_id"])
        db.commit()
        flash("Veículo cadastrado.", "success")
    except (ValidationError, ValueError, sqlite3.IntegrityError):
        flash("Não foi possível cadastrar o veículo. Confira placa, ano e dados duplicados.", "error")
    return redirect(url_for("index"))


@vehicles_bp.route("/vehicles/<int:vehicle_id>", methods=["POST"])
@login_required(role="admin")
@csrf_protect
def update_vehicle(vehicle_id):
    try:
        name = required(request.form, "name", "Nome")
        plate = normalized_plate(required(request.form, "plate", "Placa"))
        year, status = int(required(request.form, "year", "Ano")), request.form.get("status")
        if not 1900 <= year <= date.today().year + 1 or status not in VALID_VEHICLE_STATUS:
            raise ValidationError("Dados inválidos.")
        db = get_db()
        db.execute("UPDATE vehicles SET name=?, plate=?, year=?, status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (name, plate, year, status, vehicle_id))
        audit(db, "update", "vehicle", vehicle_id, user_id=session["user_id"])
        db.commit()
        flash("Veículo atualizado.", "success")
    except (ValidationError, ValueError, sqlite3.IntegrityError):
        flash("Não foi possível atualizar o veículo.", "error")
    return redirect(url_for("index"))


@vehicles_bp.route("/vehicles/<int:vehicle_id>/delete", methods=["POST"])
@login_required(role="admin")
@csrf_protect
def delete_vehicle(vehicle_id):
    db = get_db()
    open_use = db.execute("SELECT 1 FROM checkins WHERE vehicle_id=? AND checkout_at IS NULL", (vehicle_id,)).fetchone()
    if open_use:
        flash("Não é possível inativar um veículo em uso.", "error")
    else:
        db.execute("UPDATE vehicles SET status='Inativo', updated_at=CURRENT_TIMESTAMP WHERE id=?", (vehicle_id,))
        audit(db, "deactivate", "vehicle", vehicle_id, user_id=session["user_id"])
        db.commit()
        flash("Veículo inativado; o histórico foi preservado.", "success")
    return redirect(url_for("index"))
