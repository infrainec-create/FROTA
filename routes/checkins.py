from datetime import date
from flask import Blueprint, flash, redirect, request, session, url_for
from auth import login_required
from database import audit, get_db
from security import csrf_protect
from validators import ValidationError, positive_number, required, valid_date

checkins_bp = Blueprint("checkins", __name__)


def _last_odometer(db, vehicle_id):
    row = db.execute("""
        SELECT MAX(value) AS odometer FROM (
          SELECT odometer_start AS value FROM checkins WHERE vehicle_id=?
          UNION ALL SELECT odometer_end FROM checkins WHERE vehicle_id=?
          UNION ALL SELECT odometer FROM fuel WHERE vehicle_id=?
          UNION ALL SELECT odometer FROM maintenance WHERE vehicle_id=?
        ) WHERE value IS NOT NULL
    """, (vehicle_id, vehicle_id, vehicle_id, vehicle_id)).fetchone()
    return row["odometer"] or 0


@checkins_bp.route("/checkins", methods=["POST"])
@login_required()
@csrf_protect
def create_checkin():
    try:
        vehicle_id, driver_id = int(required(request.form, "vehicle_id", "Veículo")), int(required(request.form, "driver_id", "Motorista"))
        checkin_date, start = valid_date(request.form, "checkin_at", "Data de entrada"), positive_number(request.form, "odometer_start", "Odômetro")
        db = get_db()
        vehicle = db.execute("SELECT * FROM vehicles WHERE id=?", (vehicle_id,)).fetchone()
        driver = db.execute("SELECT * FROM drivers WHERE id=?", (driver_id,)).fetchone()
        if not vehicle or vehicle["status"] != "Disponível": raise ValidationError("Selecione um veículo disponível.")
        if not driver or driver["status"] != "Ativo": raise ValidationError("Selecione um motorista ativo.")
        expiry_str = driver["license_expiry"]
        if not expiry_str or date.fromisoformat(expiry_str) < checkin_date: raise ValidationError("A CNH do motorista está vencida ou não informada.")
        if session["role"] == "driver":
            # Um motorista só pode registrar o uso associado ao próprio CPF/CNH, se houver vínculo cadastrado pelo admin.
            flash("Check-in deve ser registrado pelo administrador.", "error")
            return redirect(url_for("index"))
        if db.execute("SELECT 1 FROM checkins WHERE vehicle_id=? AND checkout_at IS NULL", (vehicle_id,)).fetchone(): raise ValidationError("Este veículo já possui check-in aberto.")
        if start < _last_odometer(db, vehicle_id): raise ValidationError("Odômetro menor que a última quilometragem registrada.")
        cursor = db.execute("INSERT INTO checkins (vehicle_id,driver_id,checkin_at,notes,odometer_start) VALUES (?,?,?,?,?)", (vehicle_id, driver_id, checkin_date.isoformat(), request.form.get("notes", "").strip()[:1000], start))
        db.execute("UPDATE vehicles SET status='Em uso', updated_at=CURRENT_TIMESTAMP WHERE id=?", (vehicle_id,))
        audit(db, "checkin", "checkin", cursor.lastrowid, user_id=session["user_id"]); db.commit(); flash("Check-in registrado.", "success")
    except (ValidationError, ValueError, TypeError): flash("Não foi possível registrar o check-in. Verifique os dados.", "error")
    return redirect(url_for("index"))


@checkins_bp.route("/checkins/<int:checkin_id>/checkout", methods=["POST"])
@login_required(role="admin")
@csrf_protect
def checkout_checkin(checkin_id):
    try:
        end_date, end = valid_date(request.form, "checkout_at", "Data de saída"), positive_number(request.form, "odometer_end", "Odômetro")
        db = get_db(); checkin = db.execute("SELECT * FROM checkins WHERE id=?", (checkin_id,)).fetchone()
        if not checkin or checkin["checkout_at"]: raise ValidationError("Check-in não encontrado ou já finalizado.")
        if end_date < date.fromisoformat(checkin["checkin_at"]) or end < checkin["odometer_start"]: raise ValidationError("Data ou odômetro de chegada inválidos.")
        db.execute("UPDATE checkins SET checkout_at=?, odometer_end=? WHERE id=?", (end_date.isoformat(), end, checkin_id))
        db.execute("UPDATE vehicles SET status='Disponível', updated_at=CURRENT_TIMESTAMP WHERE id=?", (checkin["vehicle_id"],))
        audit(db, "checkout", "checkin", checkin_id, user_id=session["user_id"]); db.commit(); flash("Check-out registrado.", "success")
    except (ValidationError, ValueError): flash("Não foi possível finalizar o check-in.", "error")
    return redirect(url_for("index"))
