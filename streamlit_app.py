from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from drive_repository import DriveRepository
from maintenance_ai import analyze_maintenance


st.set_page_config(page_title="FrotaControl", page_icon="🚚", layout="wide")


def secret(name: str, default: Any = None) -> Any:
    return st.secrets[name] if name in st.secrets else default


@st.cache_resource
def repository() -> DriveRepository:
    account = secret("gcp_service_account")
    spreadsheet_id = secret("google_sheet_id")
    if not account or not spreadsheet_id:
        raise RuntimeError("Configure gcp_service_account e google_sheet_id em .streamlit/secrets.toml.")
    return DriveRepository(dict(account), str(spreadsheet_id))


def rows(table: str) -> list[dict[str, Any]]:
    return repository().list(table)


def as_number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def vehicle_label(vehicle: dict[str, Any]) -> str:
    return f"{vehicle['name']} · {vehicle['plate']}"


def vehicle_odometer(vehicle_id: str, fuel: list[dict[str, Any]], maintenance: list[dict[str, Any]], checkins: list[dict[str, Any]]) -> float:
    values = []
    for item in fuel + maintenance:
        if item.get("vehicle_id") == vehicle_id:
            values.append(as_number(item.get("odometer")))
    for item in checkins:
        if item.get("vehicle_id") == vehicle_id:
            values.extend([as_number(item.get("odometer_start")), as_number(item.get("odometer_end"))])
    return max(values, default=0.0)


try:
    repo = repository()
except Exception as exc:
    st.title("🚚 FrotaControl")
    st.error("O banco de dados no Google Drive ainda não foi conectado.")
    st.code(str(exc), language=None)
    st.info("Siga a seção 'Configuração do Streamlit Cloud' no README. Nenhuma credencial deve ser enviada ao GitHub.")
    st.stop()

vehicles, drivers, maintenance, fuel, checkins, fines = (rows(name) for name in ("vehicles", "drivers", "maintenance", "fuel", "checkins", "fines"))
st.title("🚚 FrotaControl")
st.caption("Gestão de frota com dados privados no Google Drive")

tab_dashboard, tab_vehicles, tab_operations, tab_maintenance, tab_reports, tab_ai = st.tabs([
    "Painel", "Veículos e motoristas", "Operações", "Manutenção", "Relatórios", "Analista IA",
])

with tab_dashboard:
    active = sum(v.get("status") == "Disponível" for v in vehicles)
    in_maintenance = sum(v.get("status") == "Manutenção" for v in vehicles)
    total_maint = sum(as_number(m.get("cost")) for m in maintenance)
    total_fuel = sum(as_number(f.get("cost")) for f in fuel)
    a, b, c, d = st.columns(4)
    a.metric("Veículos", len(vehicles))
    b.metric("Disponíveis", active)
    c.metric("Em manutenção", in_maintenance)
    d.metric("Custo registrado", f"R$ {total_maint + total_fuel:,.2f}")
    alerts = []
    for vehicle in vehicles:
        current = vehicle_odometer(vehicle["id"], fuel, maintenance, checkins)
        history = [as_number(m.get("odometer")) for m in maintenance if m.get("vehicle_id") == vehicle["id"]]
        if current >= 10000 and (not history or current - max(history) >= 10000):
            alerts.append(f"{vehicle_label(vehicle)}: revisão preventiva recomendada (odômetro: {current:,.0f} km).")
    if alerts:
        st.warning("\n\n".join(alerts))
    else:
        st.success("Nenhum alerta preventivo calculado no momento.")

with tab_vehicles:
    left, right = st.columns(2)
    with left:
        st.subheader("Cadastrar veículo")
        with st.form("new_vehicle", clear_on_submit=True):
            name = st.text_input("Modelo / nome")
            plate = st.text_input("Placa").upper().strip()
            year = st.number_input("Ano", 1900, 2100, value=date.today().year)
            status = st.selectbox("Situação", ["Disponível", "Em uso", "Manutenção", "Inativo"])
            if st.form_submit_button("Salvar veículo"):
                if not name or not plate:
                    st.error("Informe nome e placa.")
                elif any(v.get("plate") == plate for v in vehicles):
                    st.error("Esta placa já está cadastrada.")
                else:
                    repo.add("vehicles", {"name": name.strip(), "plate": plate, "year": year, "status": status})
                    st.rerun()
    with right:
        st.subheader("Cadastrar motorista")
        with st.form("new_driver", clear_on_submit=True):
            name = st.text_input("Nome")
            phone = st.text_input("Telefone")
            license_number = st.text_input("CNH")
            expiry = st.date_input("Vencimento da CNH", value=None)
            if st.form_submit_button("Salvar motorista"):
                if not name or not license_number:
                    st.error("Informe nome e CNH.")
                else:
                    repo.add("drivers", {"name": name.strip(), "phone": phone.strip(), "license": license_number.strip(), "license_expiry": expiry, "status": "Ativo"})
                    st.rerun()
    if vehicles:
        st.dataframe(pd.DataFrame(vehicles)[["name", "plate", "year", "status"]], use_container_width=True, hide_index=True)

with tab_operations:
    st.subheader("Operação de veículos")
    if not vehicles:
        st.info("Cadastre um veículo para registrar operações.")
    else:
        by_label = {vehicle_label(v): v for v in vehicles if v.get("status") != "Inativo"}
        with st.form("new_fuel", clear_on_submit=True):
            selected = st.selectbox("Veículo", list(by_label))
            col1, col2, col3 = st.columns(3)
            liters = col1.number_input("Litros", min_value=0.01, step=1.0)
            cost = col2.number_input("Custo (R$)", min_value=0.01, step=1.0)
            odometer = col3.number_input("Odômetro", min_value=0.0, step=1.0)
            fuel_date = st.date_input("Data", value=date.today())
            if st.form_submit_button("Registrar abastecimento"):
                vehicle = by_label[selected]
                if odometer < vehicle_odometer(vehicle["id"], fuel, maintenance, checkins):
                    st.error("O odômetro não pode ser menor que o último registro.")
                else:
                    repo.add("fuel", {"vehicle_id": vehicle["id"], "liters": liters, "cost": cost, "fuel_date": fuel_date, "odometer": odometer})
                    st.rerun()
        st.divider()
        left, right = st.columns(2)
        with left:
            st.subheader("Abrir check-in")
            active_drivers = [driver for driver in drivers if driver.get("status") == "Ativo"]
            available_vehicles = [vehicle for vehicle in vehicles if vehicle.get("status") == "Disponível"]
            if not active_drivers or not available_vehicles:
                st.info("É necessário ter um motorista ativo e um veículo disponível.")
            else:
                vehicle_options = {vehicle_label(vehicle): vehicle for vehicle in available_vehicles}
                driver_options = {driver["name"]: driver for driver in active_drivers}
                with st.form("new_checkin", clear_on_submit=True):
                    selected_vehicle = st.selectbox("Veículo", list(vehicle_options), key="checkin_vehicle")
                    selected_driver = st.selectbox("Motorista", list(driver_options))
                    start = st.number_input("Odômetro de saída", min_value=0.0, step=1.0)
                    checkin_date = st.date_input("Data de saída", value=date.today(), key="checkin_date")
                    notes = st.text_area("Observações")
                    if st.form_submit_button("Abrir check-in"):
                        vehicle = vehicle_options[selected_vehicle]
                        if start < vehicle_odometer(vehicle["id"], fuel, maintenance, checkins):
                            st.error("O odômetro não pode ser menor que o último registro.")
                        else:
                            repo.add("checkins", {"vehicle_id": vehicle["id"], "driver_id": driver_options[selected_driver]["id"], "checkin_at": checkin_date, "checkout_at": "", "odometer_start": start, "odometer_end": "", "notes": notes.strip()})
                            repo.update("vehicles", vehicle["id"], {"status": "Em uso"})
                            st.rerun()
        with right:
            st.subheader("Finalizar check-in")
            open_checkins = [item for item in checkins if not item.get("checkout_at")]
            if not open_checkins:
                st.info("Não há check-ins abertos.")
            else:
                checkin_options = {
                    f"{vehicle_label(next(v for v in vehicles if v['id'] == item['vehicle_id']))} · {item['checkin_at']}": item
                    for item in open_checkins
                }
                with st.form("checkout", clear_on_submit=True):
                    selected_checkin = st.selectbox("Check-in", list(checkin_options))
                    end = st.number_input("Odômetro de chegada", min_value=0.0, step=1.0)
                    checkout_date = st.date_input("Data de chegada", value=date.today(), key="checkout_date")
                    if st.form_submit_button("Finalizar check-in"):
                        checkin = checkin_options[selected_checkin]
                        if end < as_number(checkin.get("odometer_start")):
                            st.error("O odômetro de chegada não pode ser menor que o de saída.")
                        else:
                            repo.update("checkins", checkin["id"], {"checkout_at": checkout_date, "odometer_end": end})
                            repo.update("vehicles", checkin["vehicle_id"], {"status": "Disponível"})
                            st.rerun()

with tab_maintenance:
    st.subheader("Registrar manutenção")
    if vehicles:
        by_label = {vehicle_label(v): v for v in vehicles if v.get("status") != "Inativo"}
        with st.form("new_maintenance", clear_on_submit=True):
            selected = st.selectbox("Veículo", list(by_label), key="maintenance_vehicle")
            description = st.text_area("Serviço executado")
            col1, col2 = st.columns(2)
            cost = col1.number_input("Custo (R$)", min_value=0.01, step=1.0, key="maintenance_cost")
            odometer = col2.number_input("Odômetro", min_value=0.0, step=1.0, key="maintenance_odometer")
            maint_date = st.date_input("Data", value=date.today(), key="maintenance_date")
            if st.form_submit_button("Registrar manutenção"):
                vehicle = by_label[selected]
                if not description.strip():
                    st.error("Descreva o serviço executado.")
                elif odometer < vehicle_odometer(vehicle["id"], fuel, maintenance, checkins):
                    st.error("O odômetro não pode ser menor que o último registro.")
                else:
                    repo.add("maintenance", {"vehicle_id": vehicle["id"], "description": description.strip(), "cost": cost, "maint_date": maint_date, "odometer": odometer})
                    st.rerun()
    if maintenance:
        display = pd.DataFrame(maintenance)
        display["cost"] = display["cost"].map(lambda x: f"R$ {as_number(x):,.2f}")
        st.dataframe(display[["maint_date", "description", "cost", "odometer"]], use_container_width=True, hide_index=True)

with tab_reports:
    report_name = st.selectbox("Dados para exportar", ["vehicles", "maintenance", "fuel", "drivers"])
    data = rows(report_name)
    if data:
        frame = pd.DataFrame(data)
        st.dataframe(frame, use_container_width=True, hide_index=True)
        st.download_button("Baixar CSV", frame.to_csv(index=False).encode("utf-8-sig"), f"frota_{report_name}.csv", "text/csv")
    else:
        st.info("Ainda não há dados nesta categoria.")

with tab_ai:
    st.subheader("Analista de IA — manutenção")
    st.caption("Analisa o histórico cadastrado e sugere prioridades; não agenda nem executa serviços automaticamente.")
    api_key = secret("OPENAI_API_KEY")
    if not api_key:
        st.info("Para ativar o analista, adicione OPENAI_API_KEY aos secrets do Streamlit.")
    elif not vehicles:
        st.info("Cadastre um veículo e seu histórico de manutenção para começar.")
    else:
        selected = st.selectbox("Veículo a analisar", [vehicle_label(v) for v in vehicles], key="ai_vehicle")
        vehicle = next(v for v in vehicles if vehicle_label(v) == selected)
        if st.button("Gerar parecer", type="primary"):
            with st.spinner("Analisando histórico..."):
                try:
                    answer = analyze_maintenance(
                        str(api_key), vehicle,
                        [m for m in maintenance if m.get("vehicle_id") == vehicle["id"]],
                        [f for f in fuel if f.get("vehicle_id") == vehicle["id"]],
                    )
                    st.markdown(answer)
                except Exception:
                    st.error("Não foi possível gerar o parecer agora. Confira a chave da API e tente novamente.")
