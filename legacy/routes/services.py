from flask import Blueprint, flash, redirect, request, session, url_for
from auth import login_required
from database import audit, get_db
from routes.checkins import _last_odometer
from security import csrf_protect
from validators import VALID_FINE_STATUS, ValidationError, positive_number, required, valid_date

services_bp = Blueprint("services", __name__)


def _vehicle_and_odometer():
    vehicle_id = int(required(request.form, "vehicle_id", "Veículo")); db = get_db()
    vehicle = db.execute("SELECT status FROM vehicles WHERE id=?", (vehicle_id,)).fetchone()
    if not vehicle or vehicle["status"] == "Inativo": raise ValidationError("Veículo inválido ou inativo.")
    odometer = positive_number(request.form, "odometer", "Odômetro", allow_zero=True)
    if odometer < _last_odometer(db, vehicle_id): raise ValidationError("Odômetro menor que a última quilometragem registrada.")
    return db, vehicle_id, odometer


@services_bp.route("/maintenance", methods=["POST"])
@login_required(role="admin")
@csrf_protect
def create_maintenance():
    try:
        db, vehicle_id, odometer = _vehicle_and_odometer()
        cursor = db.execute("INSERT INTO maintenance (vehicle_id,description,cost,maint_date,odometer) VALUES (?,?,?,?,?)", (vehicle_id, required(request.form, "description", "Descrição"), positive_number(request.form, "cost", "Custo"), valid_date(request.form, "maint_date", "Data").isoformat(), odometer))
        db.execute("UPDATE vehicles SET status='Disponível' WHERE id=? AND status='Manutenção'", (vehicle_id,))
        audit(db, "create", "maintenance", cursor.lastrowid, user_id=session["user_id"]); db.commit(); flash("Manutenção registrada.", "success")
    except (ValidationError, ValueError): flash("Não foi possível registrar a manutenção.", "error")
    return redirect(url_for("index"))


@services_bp.route("/fuel", methods=["POST"])
@login_required(role="admin")
@csrf_protect
def create_fuel():
    try:
        db, vehicle_id, odometer = _vehicle_and_odometer()
        cursor = db.execute("INSERT INTO fuel (vehicle_id,liters,cost,fuel_date,odometer) VALUES (?,?,?,?,?)", (vehicle_id, positive_number(request.form, "liters", "Litros"), positive_number(request.form, "cost", "Custo"), valid_date(request.form, "fuel_date", "Data").isoformat(), odometer))
        audit(db, "create", "fuel", cursor.lastrowid, user_id=session["user_id"]); db.commit(); flash("Abastecimento registrado.", "success")
    except (ValidationError, ValueError): flash("Não foi possível registrar o abastecimento.", "error")
    return redirect(url_for("index"))


@services_bp.route("/fines", methods=["POST"])
@login_required(role="admin")
@csrf_protect
def create_fine():
    try:
        driver_id = int(required(request.form, "driver_id", "Motorista")); db = get_db()
        if not db.execute("SELECT 1 FROM drivers WHERE id=?", (driver_id,)).fetchone(): raise ValidationError("Motorista inválido.")
        status = request.form.get("status")
        if status not in VALID_FINE_STATUS: raise ValidationError("Status de multa inválido.")
        cursor = db.execute("INSERT INTO fines (driver_id,description,amount,fine_date,status) VALUES (?,?,?,?,?)", (driver_id, required(request.form, "description", "Descrição"), positive_number(request.form, "amount", "Valor"), valid_date(request.form, "fine_date", "Data").isoformat(), status))
        audit(db, "create", "fine", cursor.lastrowid, user_id=session["user_id"]); db.commit(); flash("Multa registrada.", "success")
    except (ValidationError, ValueError): flash("Não foi possível registrar a multa.", "error")
    return redirect(url_for("index"))
