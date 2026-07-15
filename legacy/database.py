import os
import sqlite3
from datetime import datetime, timezone
from flask import current_app, g
from werkzeug.security import generate_password_hash


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(current_app.config["FROTA_DB"])
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
    return db


def audit(db, action, entity, entity_id=None, details=None, user_id=None):
    db.execute(
        "INSERT INTO audit_log (user_id, action, entity, entity_id, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, action, entity, entity_id, details, datetime.now(timezone.utc).isoformat()),
    )


def init_db(db_path=None):
    db_path = db_path or os.getenv("FROTA_DB", "frota.db")
    db = sqlite3.connect(db_path)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, plate TEXT NOT NULL UNIQUE,
            year INTEGER NOT NULL CHECK(year BETWEEN 1900 AND 2100),
            status TEXT NOT NULL CHECK(status IN ('Disponível','Em uso','Manutenção','Inativo')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS drivers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, cpf TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL, license TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('Ativo','Inativo')),
            license_expiry TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT, vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE RESTRICT,
            driver_id INTEGER NOT NULL REFERENCES drivers(id) ON DELETE RESTRICT, checkin_at TEXT NOT NULL,
            checkout_at TEXT, notes TEXT, odometer_start REAL NOT NULL CHECK(odometer_start >= 0),
            odometer_end REAL CHECK(odometer_end >= odometer_start), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS maintenance (
            id INTEGER PRIMARY KEY AUTOINCREMENT, vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE RESTRICT,
            description TEXT NOT NULL, cost REAL NOT NULL CHECK(cost > 0), maint_date TEXT NOT NULL,
            odometer REAL NOT NULL CHECK(odometer >= 0), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS fuel (
            id INTEGER PRIMARY KEY AUTOINCREMENT, vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE RESTRICT,
            liters REAL NOT NULL CHECK(liters > 0), cost REAL NOT NULL CHECK(cost > 0), fuel_date TEXT NOT NULL,
            odometer REAL NOT NULL CHECK(odometer >= 0), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS fines (
            id INTEGER PRIMARY KEY AUTOINCREMENT, driver_id INTEGER NOT NULL REFERENCES drivers(id) ON DELETE RESTRICT,
            description TEXT NOT NULL, amount REAL NOT NULL CHECK(amount > 0), fine_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Pendente','Pago','Contestada')), external_id TEXT UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','driver')), status TEXT NOT NULL DEFAULT 'Pendente'
                CHECK(status IN ('Pendente','Aprovado','Bloqueado')), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            action TEXT NOT NULL, entity TEXT NOT NULL, entity_id INTEGER, details TEXT, created_at TEXT NOT NULL
        );
    """)
    # Compatibilidade com bancos criados por versões anteriores.
    for statement in (
        "ALTER TABLE checkins ADD COLUMN odometer_start REAL",
        "ALTER TABLE checkins ADD COLUMN odometer_end REAL",
        "ALTER TABLE drivers ADD COLUMN license_expiry TEXT",
        "ALTER TABLE maintenance ADD COLUMN maint_date TEXT",
        "ALTER TABLE maintenance ADD COLUMN odometer REAL",
        "ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'Aprovado'",
        "ALTER TABLE fines ADD COLUMN external_id TEXT",
    ):
        try:
            db.execute(statement)
        except sqlite3.OperationalError:
            pass
    # Criação de índices (após garantir a presença de todas as colunas)
    for statement in (
        "CREATE INDEX IF NOT EXISTS idx_checkins_open ON checkins(vehicle_id, checkout_at)",
        "CREATE INDEX IF NOT EXISTS idx_fuel_vehicle_date ON fuel(vehicle_id, fuel_date)",
        "CREATE INDEX IF NOT EXISTS idx_maintenance_vehicle_date ON maintenance(vehicle_id, maint_date)",
        "CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_log(created_at)",
    ):
        try:
            db.execute(statement)
        except sqlite3.OperationalError:
            pass
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
    if password and not db.execute("SELECT 1 FROM users WHERE role = 'admin'").fetchone():
        db.execute("INSERT INTO users (username, password_hash, role, status) VALUES (?, ?, 'admin', 'Aprovado')",
                   (username, generate_password_hash(password)))
    db.commit()
    db.close()
