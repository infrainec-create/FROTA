import csv
import io
from flask import Blueprint, make_response
from database import get_db
from auth import login_required

reports_bp = Blueprint("reports", __name__)

@reports_bp.route("/reports/export/<string:report_type>", methods=["GET"])
@login_required(role="admin")
def export_report(report_type):
    db = get_db()
    
    si = io.StringIO()
    # Excel compatibility BOM prefix
    si.write('\ufeff')
    writer = csv.writer(si, delimiter=';')
    
    if report_type == "checkins":
        writer.writerow(["ID Checkin", "Veículo", "Placa", "Motorista", "Saída", "Chegada", "KM Saída", "KM Chegada", "Notas"])
        rows = db.execute(
            """
            SELECT c.id, v.name as vehicle_name, v.plate as vehicle_plate, d.name as driver_name,
                   c.checkin_at, c.checkout_at, c.odometer_start, c.odometer_end, c.notes
            FROM checkins c
            LEFT JOIN vehicles v ON c.vehicle_id = v.id
            LEFT JOIN drivers d ON c.driver_id = d.id
            ORDER BY c.id DESC
            """
        ).fetchall()
        for r in rows:
            writer.writerow([
                r["id"],
                r["vehicle_name"],
                r["vehicle_plate"],
                r["driver_name"],
                r["checkin_at"],
                r["checkout_at"] or "-",
                r["odometer_start"] or "-",
                r["odometer_end"] or "-",
                r["notes"] or ""
            ])
            
    elif report_type == "maintenance":
        writer.writerow(["ID Manutenção", "Veículo", "Placa", "Descrição", "Custo (R$)", "Data", "Odômetro (km)"])
        rows = db.execute(
            """
            SELECT m.id, v.name as vehicle_name, v.plate as vehicle_plate, m.description, m.cost, m.maint_date, m.odometer
            FROM maintenance m
            LEFT JOIN vehicles v ON m.vehicle_id = v.id
            ORDER BY m.id DESC
            """
        ).fetchall()
        for r in rows:
            writer.writerow([
                r["id"],
                r["vehicle_name"],
                r["vehicle_plate"],
                r["description"],
                f"{r['cost']:.2f}".replace(".", ","),
                r["maint_date"],
                r["odometer"] or "-"
            ])
            
    elif report_type == "fuel":
        writer.writerow(["ID Abastecimento", "Veículo", "Placa", "Litros", "Custo (R$)", "Data", "Odômetro (km)"])
        rows = db.execute(
            """
            SELECT f.id, v.name as vehicle_name, v.plate as vehicle_plate, f.liters, f.cost, f.fuel_date, f.odometer
            FROM fuel f
            LEFT JOIN vehicles v ON f.vehicle_id = v.id
            ORDER BY f.id DESC
            """
        ).fetchall()
        for r in rows:
            writer.writerow([
                r["id"],
                r["vehicle_name"],
                r["vehicle_plate"],
                f"{r['liters']:.2f}".replace(".", ","),
                f"{r['cost']:.2f}".replace(".", ","),
                r["fuel_date"],
                r["odometer"] or "-"
            ])
            
    elif report_type == "fines":
        writer.writerow(["ID Multa", "Motorista", "Descrição", "Valor (R$)", "Data", "Status"])
        rows = db.execute(
            """
            SELECT f.id, d.name as driver_name, f.description, f.amount, f.fine_date, f.status
            FROM fines f
            LEFT JOIN drivers d ON f.driver_id = d.id
            ORDER BY f.id DESC
            """
        ).fetchall()
        for r in rows:
            writer.writerow([
                r["id"],
                r["driver_name"],
                r["description"],
                f"{r['amount']:.2f}".replace(".", ","),
                r["fine_date"],
                r["status"]
            ])
    else:
        return "Tipo de relatório inválido", 400
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=relatorio_{report_type}.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output
