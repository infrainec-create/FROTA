import os
from datetime import datetime, timedelta
from flask import Flask, render_template, g, session, request, redirect, url_for
from database import get_db, init_db
from auth import auth_bp, login_required
from routes.vehicles import vehicles_bp
from routes.drivers import drivers_bp
from routes.checkins import checkins_bp
from routes.services import services_bp
from routes.detran import detran_bp
from routes.reports import reports_bp
from routes.users import users_bp
from security import configure_security

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or os.urandom(32)
app.config["FROTA_DB"] = os.getenv("FROTA_DB", "frota.db")
configure_security(app)

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(vehicles_bp)
app.register_blueprint(drivers_bp)
app.register_blueprint(checkins_bp)
app.register_blueprint(services_bp)
app.register_blueprint(detran_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(users_bp)

@app.before_request
def sync_user_session():
    if "user_id" in session:
        if request.endpoint == 'auth.logout':
            return
        db = get_db()
        user = db.execute("SELECT role, status, username FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if not user or user["status"] != "Aprovado":
            session.clear()
            return redirect(url_for("auth.login"))
        session["role"] = user["role"]
        session["username"] = user["username"]

@app.teardown_appcontext
def close_db(error):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

@app.template_filter("mask_cpf")
def mask_cpf(value):
    value = str(value or "")
    return f"***.***.***-{value[-2:]}" if len(value) >= 2 else "***"

@app.route("/")
@login_required()
def index():
    db = get_db()
    is_admin = session.get("role") == "admin"
    vehicles = db.execute("SELECT * FROM vehicles ORDER BY id DESC").fetchall()
    drivers = db.execute("SELECT * FROM drivers ORDER BY id DESC").fetchall() if is_admin else []
    
    checkins = db.execute(
        """
        SELECT c.*, v.name AS vehicle_name, v.plate AS vehicle_plate, d.name AS driver_name
        FROM checkins c
        LEFT JOIN vehicles v ON c.vehicle_id = v.id
        LEFT JOIN drivers d ON c.driver_id = d.id
        ORDER BY c.id DESC
        """
    ).fetchall() if is_admin else []
    
    maintenance = db.execute(
        """
        SELECT m.*, v.name AS vehicle_name, v.plate AS vehicle_plate
        FROM maintenance m
        LEFT JOIN vehicles v ON m.vehicle_id = v.id
        ORDER BY m.id DESC
        """
    ).fetchall() if is_admin else []
    
    fuel = db.execute(
        """
        SELECT f.*, v.name AS vehicle_name, v.plate AS vehicle_plate
        FROM fuel f
        LEFT JOIN vehicles v ON f.vehicle_id = v.id
        ORDER BY f.id DESC
        """
    ).fetchall() if is_admin else []
    
    fines = db.execute(
        """
        SELECT fi.*, d.name AS driver_name
        FROM fines fi
        LEFT JOIN drivers d ON fi.driver_id = d.id
        ORDER BY fi.id DESC
        """
    ).fetchall() if is_admin else []

    # Calculations for stats
    total_vehicles = db.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] or 0
    total_drivers = (db.execute("SELECT COUNT(*) FROM drivers").fetchone()[0] or 0) if is_admin else 0
    active_checkins = db.execute("SELECT COUNT(*) FROM checkins WHERE checkout_at IS NULL").fetchone()[0] or 0
    
    total_maintenance_cost = (db.execute("SELECT SUM(cost) FROM maintenance").fetchone()[0] or 0.0) if is_admin else 0.0
    total_fuel_cost = (db.execute("SELECT SUM(cost) FROM fuel").fetchone()[0] or 0.0) if is_admin else 0.0
    total_fines_cost = (db.execute("SELECT SUM(amount) FROM fines").fetchone()[0] or 0.0) if is_admin else 0.0
    
    status_available = db.execute("SELECT COUNT(*) FROM vehicles WHERE status = 'Disponível'").fetchone()[0] or 0
    status_in_use = db.execute("SELECT COUNT(*) FROM vehicles WHERE status = 'Em uso'").fetchone()[0] or 0
    status_maint = db.execute("SELECT COUNT(*) FROM vehicles WHERE status = 'Manutenção'").fetchone()[0] or 0

    stats = {
        "total_vehicles": total_vehicles,
        "total_drivers": total_drivers,
        "active_checkins": active_checkins,
        "total_maintenance_cost": total_maintenance_cost,
        "total_fuel_cost": total_fuel_cost,
        "total_fines_cost": total_fines_cost,
        "status_available": status_available,
        "status_in_use": status_in_use,
        "status_maint": status_maint,
    }

    # Calculate alerts
    alerts = []
    today = datetime.now()
    in_30_days_date = today + timedelta(days=30)
    
    # 1. Driver CNH Expiration alerts
    for driver in drivers:
        expiry_str = driver["license_expiry"]
        if expiry_str:
            try:
                expiry_dt = datetime.strptime(expiry_str, "%Y-%m-%d")
                if expiry_dt <= today:
                    alerts.append({
                        "type": "danger",
                        "category": "CNH Vencida",
                        "message": f"A CNH do motorista <strong>{driver['name']}</strong> venceu em {expiry_dt.strftime('%d/%m/%Y')}!"
                    })
                elif expiry_dt <= in_30_days_date:
                    alerts.append({
                        "type": "warning",
                        "category": "CNH Próxima do Vencimento",
                        "message": f"A CNH do motorista <strong>{driver['name']}</strong> vence em {expiry_dt.strftime('%d/%m/%Y')}."
                    })
            except ValueError:
                pass

    # 2. Vehicle preventive maintenance alerts
    for vehicle in vehicles:
        vehicle_id = vehicle["id"]
        
        max_fuel_odo = db.execute("SELECT MAX(odometer) FROM fuel WHERE vehicle_id = ?", (vehicle_id,)).fetchone()[0] or 0.0
        max_checkin_start = db.execute("SELECT MAX(odometer_start) FROM checkins WHERE vehicle_id = ?", (vehicle_id,)).fetchone()[0] or 0.0
        max_checkin_end = db.execute("SELECT MAX(odometer_end) FROM checkins WHERE vehicle_id = ?", (vehicle_id,)).fetchone()[0] or 0.0
        
        current_odo = max(max_fuel_odo, max_checkin_start, max_checkin_end)
        
        last_maint_odo = db.execute("SELECT MAX(odometer) FROM maintenance WHERE vehicle_id = ?", (vehicle_id,)).fetchone()[0]
        
        if last_maint_odo is None:
            if current_odo >= 10000.0:
                alerts.append({
                    "type": "warning",
                    "category": "Revisão Necessária",
                    "message": f"O veículo <strong>{vehicle['name']} ({vehicle['plate']})</strong> atingiu {current_odo:,.0f} km e necessita de revisão preventiva (nenhuma registrada)."
                })
        else:
            diff = current_odo - last_maint_odo
            if diff >= 10000.0:
                alerts.append({
                    "type": "warning",
                    "category": "Revisão Necessária",
                    "message": f"O veículo <strong>{vehicle['name']} ({vehicle['plate']})</strong> rodou {diff:,.0f} km desde a última revisão (odômetro atual: {current_odo:,.0f} km, última: {last_maint_odo:,.0f} km)."
                })

    # Calculate vehicle costs & metrics for internal financial analysis dashboard
    vehicle_costs = []
    total_km_all = 0.0
    total_maint_all = 0.0
    total_fuel_all = 0.0
    
    for v in vehicles:
        v_id = v["id"]
        
        fuel_odos = [r["odometer"] for r in db.execute("SELECT odometer FROM fuel WHERE vehicle_id = ?", (v_id,)).fetchall() if r["odometer"] is not None]
        checkin_odos = []
        for r in db.execute("SELECT odometer_start, odometer_end FROM checkins WHERE vehicle_id = ?", (v_id,)).fetchall():
            if r["odometer_start"] is not None:
                checkin_odos.append(r["odometer_start"])
            if r["odometer_end"] is not None:
                checkin_odos.append(r["odometer_end"])
        
        all_odos = fuel_odos + checkin_odos
        v_km = (max(all_odos) - min(all_odos)) if len(all_odos) >= 2 else 0.0
        total_km_all += v_km
        
        v_fuel_cost = db.execute("SELECT SUM(cost) FROM fuel WHERE vehicle_id = ?", (v_id,)).fetchone()[0] or 0.0
        total_fuel_all += v_fuel_cost
        v_fuel_liters = db.execute("SELECT SUM(liters) FROM fuel WHERE vehicle_id = ?", (v_id,)).fetchone()[0] or 0.0
        v_maint_cost = db.execute("SELECT SUM(cost) FROM maintenance WHERE vehicle_id = ?", (v_id,)).fetchone()[0] or 0.0
        total_maint_all += v_maint_cost
        
        v_total_cost = v_fuel_cost + v_maint_cost
        v_cost_per_km = (v_total_cost / v_km) if v_km > 0 else 0.0
        v_kml = (v_km / v_fuel_liters) if v_fuel_liters > 0 else 0.0
        
        vehicle_costs.append({
            "name": v["name"],
            "plate": v["plate"],
            "fuel_cost": v_fuel_cost,
            "maint_cost": v_maint_cost,
            "total_cost": v_total_cost,
            "km": v_km,
            "cost_per_km": v_cost_per_km,
            "kml": v_kml
        })
        
    fleet_avg_cost_km = ((total_fuel_all + total_maint_all) / total_km_all) if total_km_all > 0 else 0.0
    
    most_expensive_vehicle = None
    most_efficient_vehicle = None
    if vehicle_costs:
        most_expensive_vehicle = max(vehicle_costs, key=lambda x: x["total_cost"])
        efficient_list = [vc for vc in vehicle_costs if vc["kml"] > 0]
        if efficient_list:
            most_efficient_vehicle = max(efficient_list, key=lambda x: x["kml"])

    driver_fines_ranking = db.execute(
        """
        SELECT d.name, d.cpf, COUNT(f.id) as count, SUM(f.amount) as total
        FROM fines f
        JOIN drivers d ON f.driver_id = d.id
        GROUP BY d.id
        ORDER BY total DESC
        """
    ).fetchall() if is_admin else []

    users_list = db.execute("SELECT * FROM users ORDER BY id DESC").fetchall() if is_admin else []

    return render_template(
        "index.html",
        vehicles=vehicles,
        drivers=drivers,
        checkins=checkins,
        maintenance=maintenance,
        fuel=fuel,
        fines=fines,
        stats=stats,
        alerts=alerts,
        vehicle_costs=vehicle_costs,
        fleet_avg_cost_km=fleet_avg_cost_km,
        most_expensive_vehicle=most_expensive_vehicle,
        most_efficient_vehicle=most_efficient_vehicle,
        driver_fines_ranking=driver_fines_ranking,
        users_list=users_list,
    )

if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
