"""Persistência do FrotaControl em um banco de dados SQLite sincronizado no Google Drive."""
from __future__ import annotations

from datetime import date, datetime, timezone
import os
import json
import sqlite3
import threading
from typing import Any
from uuid import uuid4

from google.oauth2.service_account import Credentials
from google.auth.transport.requests import AuthorizedSession


TABLES: dict[str, list[str]] = {
    "users": ["id", "username", "password", "name", "security_question", "security_answer", "created_at"],
    "vehicles": ["id", "name", "plate", "year", "status", "ipva_expiry", "insurance_expiry", "created_at"],
    "drivers": ["id", "name", "phone", "license", "license_expiry", "status", "created_at"],
    "maintenance": ["id", "vehicle_id", "description", "cost", "maint_date", "odometer", "maint_type", "created_at"],
    "fuel": ["id", "vehicle_id", "liters", "cost", "fuel_date", "odometer", "created_at"],
    "checkins": ["id", "vehicle_id", "driver_id", "checkin_at", "checkout_at", "odometer_start", "odometer_end", "destination", "notes", "created_at"],
    "fines": ["id", "driver_id", "description", "amount", "fine_date", "status", "created_at"],
    "expenses": ["id", "vehicle_id", "expense_type", "cost", "expense_date", "description", "created_at"],
    "audit_log": ["id", "action", "details", "created_at"],
    "config": ["key", "value"],
}


class DriveRepository:
    """Repositório de dados que utiliza um arquivo SQLite local e sincroniza no Google Drive."""

    def __init__(self, service_account: dict[str, Any] | None, google_drive_folder_id: str | None):
        self.service_account = service_account
        self.google_drive_folder_id = google_drive_folder_id
        self.db_path = "frota_drive.db"
        self.drive_file_id = None
        self.upload_lock = threading.Lock()
        self.schema_lock = threading.Lock()

        # 1. Tenta baixar o arquivo do Drive se as credenciais existirem
        self._download_from_drive()

        # 2. Garante que as tabelas e colunas SQL estão criadas e atualizadas localmente
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.schema_lock:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            for table, columns in TABLES.items():
                cols_def = []
                for col in columns:
                    if col == "id":
                        cols_def.append("id TEXT PRIMARY KEY")
                    else:
                        cols_def.append(f"{col} TEXT")
                cursor.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(cols_def)})")
                
                # Verificação e migração automática de colunas faltantes em tabelas existentes
                cursor.execute(f"PRAGMA table_info({table})")
                existing_cols = {row[1] for row in cursor.fetchall()}
                for col in columns:
                    if col not in existing_cols:
                        try:
                            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
                        except sqlite3.OperationalError:
                            pass
            conn.commit()
            conn.close()

    def _get_session(self) -> AuthorizedSession:
        scopes = ["https://www.googleapis.com/auth/drive"]
        credentials = Credentials.from_service_account_info(self.service_account, scopes=scopes)
        return AuthorizedSession(credentials)

    def _download_from_drive(self) -> None:
        if not self.service_account or not self.google_drive_folder_id:
            return

        try:
            session = self._get_session()

            # Busca se o frota.db já existe na pasta compartilhada do Drive
            q = f"name='frota.db' and '{self.google_drive_folder_id}' in parents and trashed=false"
            search_res = session.get("https://www.googleapis.com/drive/v3/files", params={"q": q, "fields": "files(id)"})
            
            if search_res.status_code == 200:
                files = search_res.json().get("files", [])
                if files:
                    self.drive_file_id = files[0]["id"]
                    # Baixa o conteúdo do arquivo
                    dl_res = session.get(f"https://www.googleapis.com/drive/v3/files/{self.drive_file_id}", params={"alt": "media"})
                    if dl_res.status_code == 200:
                        with open(self.db_path, "wb") as f:
                            f.write(dl_res.content)
                        self._ensure_schema()
        except Exception as e:
            print(f"Erro ao baixar do Drive: {e}", flush=True)

    def _upload_to_drive(self) -> None:
        if not self.service_account or not self.google_drive_folder_id:
            return

        def run_upload():
            with self.upload_lock:
                try:
                    session = self._get_session()

                    # Se não temos o ID do arquivo do Drive, tenta buscar novamente na pasta
                    if not self.drive_file_id:
                        q = f"name='frota.db' and '{self.google_drive_folder_id}' in parents and trashed=false"
                        search_res = session.get("https://www.googleapis.com/drive/v3/files", params={"q": q, "fields": "files(id)"})
                        if search_res.status_code == 200:
                            files = search_res.json().get("files", [])
                            if files:
                                self.drive_file_id = files[0]["id"]

                    uploaded_successfully = False
                    if self.drive_file_id:
                        # Atualiza o arquivo existente
                        with open(self.db_path, "rb") as f:
                            res = session.patch(
                                f"https://www.googleapis.com/upload/drive/v3/files/{self.drive_file_id}?uploadType=media",
                                data=f.read(),
                                headers={"Content-Type": "application/x-sqlite3"}
                            )
                            if res.status_code in (200, 201):
                                uploaded_successfully = True
                    else:
                        # Cria um novo arquivo dentro da pasta compartilhada do usuário
                        # (isso consome a cota de armazenamento do proprietário da pasta, não do Service Account)
                        metadata = {
                            "name": "frota.db",
                            "parents": [self.google_drive_folder_id]
                        }
                        files = {
                            "data": ("metadata", json.dumps(metadata), "application/json; charset=UTF-8"),
                            "file": ("frota.db", open(self.db_path, "rb"), "application/x-sqlite3")
                        }
                        res = session.post("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart", files=files)
                        if res.status_code in (200, 201):
                            self.drive_file_id = res.json().get("id")
                            uploaded_successfully = True

                    # Se o upload principal do frota.db deu certo, gerencia o backup rotativo nos slots do Drive
                    if uploaded_successfully:
                        self._backup_local()
                        try:
                            # 1. Determina o próximo slot
                            ultimo_slot = 1
                            conn = sqlite3.connect(self.db_path, timeout=30.0)
                            cursor = conn.cursor()
                            try:
                                cursor.execute("SELECT value FROM config WHERE key = 'ultimo_backup_slot'")
                                row = cursor.fetchone()
                                if row:
                                    ultimo_slot = int(row[0])
                            except Exception:
                                pass

                            next_slot = (ultimo_slot % 5) + 1
                            backup_name = f"frota_backup_{next_slot}.db"

                            # 2. Procura se o arquivo do slot já existe na pasta do Drive
                            q_backup = f"name='{backup_name}' and '{self.google_drive_folder_id}' in parents and trashed=false"
                            search_backup = session.get("https://www.googleapis.com/drive/v3/files", params={"q": q_backup, "fields": "files(id)"})
                            
                            if search_backup.status_code == 200:
                                files_backup = search_backup.json().get("files", [])
                                if files_backup:
                                    # Slot já existe, atualizamos ele (consumindo cota do usuário)
                                    backup_file_id = files_backup[0]["id"]
                                    with open(self.db_path, "rb") as f:
                                        session.patch(
                                            f"https://www.googleapis.com/upload/drive/v3/files/{backup_file_id}?uploadType=media",
                                            data=f.read(),
                                            headers={"Content-Type": "application/x-sqlite3"}
                                        )
                                    # Salva o slot atualizado localmente
                                    try:
                                        cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('ultimo_backup_slot', ?)", (str(next_slot),))
                                        conn.commit()
                                    except Exception:
                                        pass
                                else:
                                    # Se não existe, tenta criar
                                    metadata = {
                                        "name": backup_name,
                                        "parents": [self.google_drive_folder_id]
                                    }
                                    files = {
                                        "data": ("metadata", json.dumps(metadata), "application/json; charset=UTF-8"),
                                        "file": (backup_name, open(self.db_path, "rb"), "application/x-sqlite3")
                                    }
                                    res_create = session.post("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart", files=files)
                                    if res_create.status_code in (200, 201):
                                        try:
                                            cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('ultimo_backup_slot', ?)", (str(next_slot),))
                                            conn.commit()
                                        except Exception:
                                            pass
                            conn.close()
                        except Exception as e_backup:
                            print(f"Erro ao gerenciar backup nos slots: {e_backup}", flush=True)
                except Exception as e:
                    print(f"Erro ao subir para o Drive: {e}", flush=True)

        threading.Thread(target=run_upload, daemon=True).start()

    def list(self, table: str) -> list[dict[str, Any]]:
        self._validate_table(table)
        self._ensure_schema()
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute(f"SELECT * FROM {table}")
            rows = [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            conn.close()
            self._ensure_schema()
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {table}")
            rows = [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
        return rows

    def add(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        self._validate_table(table)
        self._ensure_schema()
        record = {
            "id": str(uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            **{k: self._serialize(v) for k, v in values.items()},
        }
        
        headers = TABLES[table]
        for h in headers:
            if h not in record:
                record[h] = ""

        columns_str = ", ".join(headers)
        placeholders = ", ".join(["?"] * len(headers))
        values_list = [record[h] for h in headers]

        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute(f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})", values_list)
            conn.commit()
        except sqlite3.OperationalError:
            conn.close()
            self._ensure_schema()
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute(f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})", values_list)
            conn.commit()
        finally:
            conn.close()
        
        self._upload_to_drive()
        return record

    def update(self, table: str, record_id: str, values: dict[str, Any]) -> None:
        self._validate_table(table)
        self._ensure_schema()
        serialized_values = {k: self._serialize(v) for k, v in values.items()}
        set_clause = ", ".join([f"{k} = ?" for k in serialized_values.keys()])
        bind_values = list(serialized_values.values()) + [str(record_id)]
        
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute(f"UPDATE {table} SET {set_clause} WHERE id = ?", bind_values)
            conn.commit()
        except sqlite3.OperationalError:
            conn.close()
            self._ensure_schema()
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute(f"UPDATE {table} SET {set_clause} WHERE id = ?", bind_values)
            conn.commit()
        finally:
            conn.close()
        
        self._upload_to_drive()

    def delete(self, table: str, record_id: str) -> None:
        self._validate_table(table)
        self._ensure_schema()
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute(f"DELETE FROM {table} WHERE id = ?", (str(record_id),))
            conn.commit()
        except sqlite3.OperationalError:
            conn.close()
            self._ensure_schema()
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM {table} WHERE id = ?", (str(record_id),))
            conn.commit()
        finally:
            conn.close()
        
        self._upload_to_drive()

    def clear_all_data(self) -> None:
        self._ensure_schema()
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        for table in TABLES.keys():
            cursor.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()
        self._upload_to_drive()

    def get_config(self, key: str, default: Any = None) -> str:
        self._ensure_schema()
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
            row = cursor.fetchone()
            val = row[0] if row is not None and len(row) > 0 else default
        except sqlite3.OperationalError:
            val = default
        finally:
            conn.close()
        return val if val is not None else default

    def set_config(self, key: str, value: Any) -> None:
        self._ensure_schema()
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
            conn.commit()
        except sqlite3.OperationalError:
            conn.close()
            self._ensure_schema()
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
            conn.commit()
        finally:
            conn.close()
        self._upload_to_drive()

    def _backup_local(self) -> None:
        try:
            backup_dir = "backups"
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)

            import glob
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"frota_backup_{timestamp}.db"
            dest_path = os.path.join(backup_dir, backup_filename)

            conn_src = sqlite3.connect(self.db_path)
            conn_dst = sqlite3.connect(dest_path)
            with conn_dst:
                conn_src.backup(conn_dst)
            conn_dst.close()
            conn_src.close()

            backups_existentes = sorted(glob.glob(os.path.join(backup_dir, "frota_backup_*.db")))
            if len(backups_existentes) > 5:
                for b in backups_existentes[:-5]:
                    try:
                        os.remove(b)
                    except Exception:
                        pass
        except Exception as e:
            print(f"Erro no backup local rotativo: {e}", flush=True)

    @staticmethod
    def _serialize(value: Any) -> str | int | float:
        if value is None:
            return ""
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return value

    @staticmethod
    def _validate_table(table: str) -> None:
        if table not in TABLES:
            raise ValueError("Tabela inválida.")
