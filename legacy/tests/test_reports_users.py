import os
import re
import sys
import tempfile
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["FROTA_DB"] = str(Path(tempfile.gettempdir()) / "frota_test_reports.db")
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "AdminPass2026"

from app import app
app.config["FROTA_DB"] = str(Path(tempfile.gettempdir()) / "frota_test_reports.db")
from database import init_db, get_db

def csrf(response):
    html = response.get_data(as_text=True)
    match = re.search(r'name="csrf_token" value="([^"]+)"', html) or re.search(r'name="csrf-token" content="([^"]+)"', html)
    return match.group(1) if match else None

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

def test_reports_rendering_and_export(client):
    # Register a vehicle, fuel, maintenance
    post(client, "/vehicles", {"name": "Test Car", "plate": "XYZ9A87", "year": "2022", "status": "Disponível"})
    post(client, "/fuel", {"vehicle_id": "1", "liters": "40.5", "cost": "250.0", "fuel_date": "2026-07-10", "odometer": "1000"})
    post(client, "/fuel", {"vehicle_id": "1", "liters": "42.0", "cost": "260.0", "fuel_date": "2026-07-11", "odometer": "1500"})
    post(client, "/maintenance", {"vehicle_id": "1", "description": "Troca Oleo", "cost": "180.0", "maint_date": "2026-07-11", "odometer": "1500"})
    
    # Check index renders reports tab details
    res = client.get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "tab-reports" in html
    assert "Test Car" in html
    assert "XYZ9A87" in html
    assert "R$ 690,00" in html or "R$ 690.00" in html  # total cost fuel(510) + maint(180)

    # Test report export CSV routes
    for rtype in ["checkins", "maintenance", "fuel", "fines"]:
        res_export = client.get(f"/reports/export/{rtype}")
        assert res_export.status_code == 200
        assert res_export.content_type.startswith("text/csv")

def test_user_management_flow(client):
    # Register a new user
    client.post("/logout", data={"csrf_token": csrf(client.get('/'))})
    page = client.get("/register")
    reg_res = client.post("/register", data={"username": "newdriver", "password": "NewDriverPassword123", "csrf_token": csrf(page)}, follow_redirects=True)
    assert "Solicitação enviada".encode() in reg_res.data
    
    # Log back in as admin
    page = client.get("/login")
    client.post("/login", data={"username": "admin", "password": "AdminPass2026", "csrf_token": csrf(page)})
    
    # Check pending users in index
    res = client.get("/")
    html = res.get_data(as_text=True)
    assert "newdriver" in html
    assert "tab-users-admin" in html
    
    # Approve user
    # Find user ID for newdriver
    import sqlite3
    db = sqlite3.connect(app.config["FROTA_DB"])
    db.row_factory = sqlite3.Row
    user = db.execute("SELECT id FROM users WHERE username = 'newdriver'").fetchone()
    assert user is not None
    user_id = user["id"]
    db.close()
    
    # POST to approve route
    appr_res = post(client, f"/admin/users/{user_id}/approve", {})
    assert "Conta aprovada como motorista.".encode() in appr_res.data
    
    # Toggle role (driver to admin)
    toggle_res = post(client, f"/admin/users/{user_id}/toggle-role", {})
    assert "Perfil atualizado.".encode() in toggle_res.data
    
    # Toggle back (admin to driver)
    toggle_res = post(client, f"/admin/users/{user_id}/toggle-role", {})
    assert "Perfil atualizado.".encode() in toggle_res.data
    
    # Change password
    change_res = post(client, f"/admin/users/{user_id}/change-password", {"new_password": "AnotherSecurePass2026"})
    assert "Senha alterada.".encode() in change_res.data
    
    # Delete/Block user
    del_res = post(client, f"/admin/users/{user_id}/delete", {})
    assert "Conta bloqueada; a auditoria foi preservada.".encode() in del_res.data
