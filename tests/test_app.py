import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["FROTA_DB"] = str(Path(tempfile.gettempdir()) / "frota_test.db")
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "AdminPass2026"

from app import app
app.config["FROTA_DB"] = str(Path(tempfile.gettempdir()) / "frota_test.db")
from database import init_db
import pytest


def csrf(response):
    html = response.get_data(as_text=True)
    match = re.search(r'name="csrf_token" value="([^"]+)"', html) or re.search(r'name="csrf-token" content="([^"]+)"', html)
    return match.group(1)


@pytest.fixture()
def client():
    path = app.config["FROTA_DB"]
    if "frota_test" not in path:
        raise RuntimeError(f"Safety guard: Refusing to delete non-test database: {path}")
    if os.path.exists(path): os.remove(path)
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    init_db(path)
    with app.test_client() as client:
        page = client.get("/login")
        client.post("/login", data={"username": "admin", "password": "AdminPass2026", "csrf_token": csrf(page)})
        yield client
    if os.path.exists(path): os.remove(path)


def post(client, url, data):
    page = client.get("/")
    data["csrf_token"] = csrf(page)
    return client.post(url, data=data, follow_redirects=True)


def test_csrf_is_required(client):
    response = client.post("/vehicles", data={"name": "Uno"})
    assert response.status_code == 400


def test_vehicle_driver_and_valid_checkin_flow(client):
    post(client, "/vehicles", {"name": "Uno", "plate": "ABC1D23", "year": "2020", "status": "Disponível"})
    post(client, "/drivers", {"name": "Maria", "cpf": "52998224725", "phone": "11999999999", "license": "123456", "status": "Ativo", "license_expiry": "2030-01-01"})
    response = post(client, "/checkins", {"vehicle_id": "1", "driver_id": "1", "checkin_at": "2026-07-11", "odometer_start": "10000", "notes": "Rota"})
    assert "Check-in registrado".encode() in response.data
    response = post(client, "/checkins/1/checkout", {"checkout_at": "2026-07-12", "odometer_end": "10100"})
    assert "Check-out registrado".encode() in response.data


def test_rejects_odometer_regression(client):
    post(client, "/vehicles", {"name": "Uno", "plate": "ABC1D23", "year": "2020", "status": "Disponível"})
    post(client, "/fuel", {"vehicle_id": "1", "liters": "10", "cost": "50", "fuel_date": "2026-07-11", "odometer": "10000"})
    response = post(client, "/maintenance", {"vehicle_id": "1", "description": "Óleo", "cost": "100", "maint_date": "2026-07-12", "odometer": "9999"})
    assert "Não foi possível registrar a manutenção".encode() in response.data


def test_registration_cannot_request_admin(client):
    client.post("/logout", data={"csrf_token": csrf(client.get('/'))})
    page = client.get("/register")
    response = client.post("/register", data={"username": "novo_usuario", "password": "SenhaForte2026", "role": "admin", "csrf_token": csrf(page)}, follow_redirects=True)
    assert "Solicitação enviada".encode() in response.data


def test_detran_requires_real_provider(client):
    response = client.post("/api/detran/consult", headers={"X-CSRF-Token": csrf(client.get('/'))}, json={"plate": "ABC1D23"})
    assert response.status_code == 503


def test_checkin_handles_missing_license_expiry(client):
    post(client, "/vehicles", {"name": "Uno", "plate": "ABC1D23", "year": "2020", "status": "Disponível"})
    import sqlite3
    db = sqlite3.connect(app.config["FROTA_DB"])
    db.execute("INSERT INTO drivers (name, cpf, phone, license, status, license_expiry) VALUES (?, ?, ?, ?, ?, ?)",
               ("Legacy Driver", "08092416338", "85994183422", "AB", "Ativo", None))
    db.commit()
    db.close()
    response = post(client, "/checkins", {"vehicle_id": "1", "driver_id": "1", "checkin_at": "2026-07-11", "odometer_start": "10000", "notes": "Rota"})
    assert "Não foi possível registrar o check-in".encode() in response.data

