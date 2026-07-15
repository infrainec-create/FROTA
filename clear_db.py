"""Script para limpar todos os dados do banco SQLite e sincronizar o banco zerado no Google Drive."""
import tomllib
from drive_repository import DriveRepository

def main():
    try:
        with open(".streamlit/secrets.toml", "rb") as file:
            secrets = tomllib.load(file)
    except FileNotFoundError:
        secrets = {}

    account = secrets.get("gcp_service_account")
    folder_id = secrets.get("google_drive_folder_id") or secrets.get("google_sheet_id")

    print("Inicializando repositório para limpeza...")
    repo = DriveRepository(account, folder_id)
    
    print("Zerando todas as tabelas...")
    repo.clear_all_data()
    print("Banco de dados completamente zerado e sincronizado no Google Drive com sucesso!")

if __name__ == "__main__":
    main()
