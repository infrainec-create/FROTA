from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
import streamlit as st

from drive_repository import DriveRepository, LocalJsonRepository
from maintenance_ai import analyze_maintenance


st.set_page_config(page_title="FrotaControl Pro", page_icon="🚚", layout="wide")


# Custom Premium Theme Styling
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', sans-serif;
}
/* Card designs */
.kpi-card {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 1.5rem;
    text-align: center;
    transition: all 0.3s ease;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    margin-bottom: 1rem;
}
.kpi-card:hover {
    transform: translateY(-2px);
    border-color: rgba(255, 255, 255, 0.15);
    background: rgba(255, 255, 255, 0.05);
}
.kpi-title {
    font-size: 0.85rem;
    color: #9ca3af;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.5rem;
}
.kpi-value {
    font-size: 2.25rem;
    font-weight: 700;
    color: #f3f4f6;
}
/* Alert cards */
.alert-card-warning {
    background-color: rgba(245, 158, 11, 0.1);
    border-left: 4px solid #f59e0b;
    padding: 1rem;
    border-radius: 8px;
    color: #eab308;
    font-size: 0.9rem;
    margin-bottom: 0.8rem;
}
.alert-card-success {
    background-color: rgba(16, 185, 129, 0.1);
    border-left: 4px solid #10b981;
    padding: 1rem;
    border-radius: 8px;
    color: #10b981;
    font-size: 0.9rem;
    margin-bottom: 0.8rem;
}
.alert-card-danger {
    background-color: rgba(239, 68, 68, 0.1);
    border-left: 4px solid #ef4444;
    padding: 1rem;
    border-radius: 8px;
    color: #ef4444;
    font-size: 0.9rem;
    margin-bottom: 0.8rem;
}
</style>
""", unsafe_allow_html=True)


def secret(name: str, default: Any = None) -> Any:
    return st.secrets[name] if name in st.secrets else default


@st.cache_resource
def get_repository() -> DriveRepository | LocalJsonRepository:
    account = secret("gcp_service_account")
    spreadsheet_id = secret("google_sheet_id")
    if not account or not spreadsheet_id:
        return LocalJsonRepository("local_db.json")
    return DriveRepository(dict(account), str(spreadsheet_id))


def rows(table: str) -> list[dict[str, Any]]:
    return get_repository().list(table)


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


repo = get_repository()

vehicles, drivers, maintenance, fuel, checkins, fines = (rows(name) for name in ("vehicles", "drivers", "maintenance", "fuel", "checkins", "fines"))

st.title("🚚 FrotaControl Pro")
st.caption("Gestão avançada de frotas com persistência flexível (Google Sheets / JSON)")

if not (secret("gcp_service_account") and secret("google_sheet_id")):
    st.warning("⚠️ Executando com banco de dados local (`local_db.json`). Para salvar os dados no Google Drive, configure o arquivo `.streamlit/secrets.toml`.")

tab_dashboard, tab_vehicles, tab_operations, tab_maintenance, tab_reports, tab_ai = st.tabs([
    "📊 Painel Geral", "👥 Veículos e Motoristas", "⚡ Operações Rápidas", "🔧 Manutenção", "📑 Relatórios & Filtros", "🤖 Analista IA"
])

with tab_dashboard:
    st.subheader("Indicadores de Desempenho (KPIs)")
    
    active = sum(v.get("status") == "Disponível" for v in vehicles)
    in_maintenance = sum(v.get("status") == "Manutenção" for v in vehicles)
    total_maint = sum(as_number(m.get("cost")) for m in maintenance)
    total_fuel = sum(as_number(f.get("cost")) for f in fuel)
    total_cost = total_maint + total_fuel
    
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Frota Total</div>
            <div class="kpi-value">{len(vehicles)}</div>
        </div>
        """, unsafe_allow_html=True)
    with col_b:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Disponíveis</div>
            <div class="kpi-value" style="color: #10b981;">{active}</div>
        </div>
        """, unsafe_allow_html=True)
    with col_c:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Em Manutenção</div>
            <div class="kpi-value" style="color: #f59e0b;">{in_maintenance}</div>
        </div>
        """, unsafe_allow_html=True)
    with col_d:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Custo Acumulado</div>
            <div class="kpi-value" style="color: #3b82f6;">R$ {total_cost:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("### 🔔 Alertas e Notificações de Manutenção")
    alerts = []
    for vehicle in vehicles:
        current = vehicle_odometer(vehicle["id"], fuel, maintenance, checkins)
        history = [as_number(m.get("odometer")) for m in maintenance if m.get("vehicle_id") == vehicle["id"]]
        if current >= 10000 and (not history or current - max(history) >= 10000):
            alerts.append(f"**{vehicle_label(vehicle)}**: revisão preventiva recomendada (odômetro atual: **{current:,.0f} km**).")
    
    if alerts:
        for alert in alerts:
            st.markdown(f'<div class="alert-card-warning">{alert}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="alert-card-success">✔️ Todos os veículos estão com a manutenção preventiva em dia!</div>', unsafe_allow_html=True)
        
    st.divider()
    
    # CHARTS SECTION
    st.subheader("Gráficos Analíticos")
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.markdown("##### ⛽ vs 🔧 Despesas Mensais por Categoria")
        costs_data = []
        for m in maintenance:
            cost_val = as_number(m.get("cost"))
            maint_date_str = m.get("maint_date")
            if maint_date_str:
                try:
                    month_str = datetime.strptime(maint_date_str[:10], "%Y-%m-%d").strftime("%Y-%m")
                    costs_data.append({"Mês": month_str, "Categoria": "Manutenção", "Valor": cost_val})
                except ValueError:
                    pass
        for f in fuel:
            cost_val = as_number(f.get("cost"))
            fuel_date_str = f.get("fuel_date")
            if fuel_date_str:
                try:
                    month_str = datetime.strptime(fuel_date_str[:10], "%Y-%m-%d").strftime("%Y-%m")
                    costs_data.append({"Mês": month_str, "Categoria": "Abastecimento", "Valor": cost_val})
                except ValueError:
                    pass
        if costs_data:
            df_costs = pd.DataFrame(costs_data)
            df_pivot = df_costs.pivot_table(index="Mês", columns="Categoria", values="Valor", aggfunc="sum").fillna(0)
            st.bar_chart(df_pivot)
        else:
            st.info("Ainda não há dados suficientes para gerar o gráfico de custos.")

    with chart_col2:
        st.markdown("##### 🚚 Status Atual da Frota")
        if vehicles:
            df_vehicles = pd.DataFrame(vehicles)
            status_counts = df_vehicles["status"].value_counts().reset_index()
            status_counts.columns = ["Status", "Quantidade"]
            st.bar_chart(status_counts.set_index("Status"))
        else:
            st.info("Cadastre veículos para ver o gráfico de status.")

with tab_vehicles:
    st.subheader("Gerenciamento de Cadastro")
    
    v_tab_view, v_tab_create, v_tab_edit, v_tab_delete = st.tabs([
        "🔍 Visualizar Dados", "➕ Novo Cadastro", "✏️ Editar Registros", "❌ Excluir Registros"
    ])
    
    with v_tab_view:
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            st.markdown("##### Veículos Cadastrados")
            if vehicles:
                st.dataframe(pd.DataFrame(vehicles)[["name", "plate", "year", "status"]], use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum veículo cadastrado.")
        with col_v2:
            st.markdown("##### Motoristas Cadastrados")
            if drivers:
                st.dataframe(pd.DataFrame(drivers)[["name", "phone", "license", "license_expiry", "status"]], use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum motorista cadastrado.")
                
    with v_tab_create:
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.markdown("##### Cadastrar Veículo")
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
                        st.success("Veículo salvo com sucesso!")
                        st.rerun()
                        
        with col_c2:
            st.markdown("##### Cadastrar Motorista")
            with st.form("new_driver", clear_on_submit=True):
                d_name = st.text_input("Nome")
                phone = st.text_input("Telefone")
                license_number = st.text_input("CNH")
                expiry = st.date_input("Vencimento da CNH", value=None)
                if st.form_submit_button("Salvar motorista"):
                    if not d_name or not license_number:
                        st.error("Informe nome e CNH.")
                    else:
                        repo.add("drivers", {"name": d_name.strip(), "phone": phone.strip(), "license": license_number.strip(), "license_expiry": expiry.isoformat() if expiry else "", "status": "Ativo"})
                        st.success("Motorista salvo com sucesso!")
                        st.rerun()
                        
    with v_tab_edit:
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            st.markdown("##### Editar Veículo")
            by_label = {vehicle_label(v): v for v in vehicles}
            selected_v_edit = st.selectbox("Selecione o veículo", [None] + list(by_label), key="edit_v_select")
            if selected_v_edit:
                v_data = by_label[selected_v_edit]
                with st.form("form_edit_vehicle"):
                    edit_name = st.text_input("Modelo / nome", value=v_data.get("name", ""))
                    edit_plate = st.text_input("Placa", value=v_data.get("plate", "")).upper().strip()
                    edit_year = st.number_input("Ano", 1900, 2100, value=int(as_number(v_data.get("year")) or date.today().year))
                    edit_status = st.selectbox("Situação", ["Disponível", "Em uso", "Manutenção", "Inativo"], index=["Disponível", "Em uso", "Manutenção", "Inativo"].index(v_data.get("status", "Disponível")))
                    if st.form_submit_button("Salvar Alterações"):
                        repo.update("vehicles", v_data["id"], {"name": edit_name.strip(), "plate": edit_plate, "year": edit_year, "status": edit_status})
                        st.success("Veículo atualizado!")
                        st.rerun()
                        
        with col_e2:
            st.markdown("##### Editar Motorista")
            drivers_map = {d["name"]: d for d in drivers}
            selected_d_edit = st.selectbox("Selecione o motorista", [None] + list(drivers_map), key="edit_d_select")
            if selected_d_edit:
                d_data = drivers_map[selected_d_edit]
                expiry_val = None
                if d_data.get("license_expiry"):
                    try:
                        expiry_val = date.fromisoformat(d_data["license_expiry"])
                    except ValueError:
                        pass
                with st.form("form_edit_driver"):
                    edit_d_name = st.text_input("Nome", value=d_data.get("name", ""))
                    edit_d_phone = st.text_input("Telefone", value=d_data.get("phone", ""))
                    edit_d_license = st.text_input("CNH", value=d_data.get("license", ""))
                    edit_d_expiry = st.date_input("Vencimento da CNH", value=expiry_val)
                    edit_d_status = st.selectbox("Status", ["Ativo", "Inativo"], index=["Ativo", "Inativo"].index(d_data.get("status", "Ativo")))
                    if st.form_submit_button("Salvar Alterações"):
                        repo.update("drivers", d_data["id"], {
                            "name": edit_d_name.strip(),
                            "phone": edit_d_phone.strip(),
                            "license": edit_d_license.strip(),
                            "license_expiry": edit_d_expiry.isoformat() if edit_d_expiry else "",
                            "status": edit_d_status
                        })
                        st.success("Motorista atualizado!")
                        st.rerun()

    with v_tab_delete:
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.markdown("##### Excluir Veículo")
            selected_v_del = st.selectbox("Selecione o veículo", [None] + list(by_label), key="del_v_select")
            if selected_v_del:
                v_data = by_label[selected_v_del]
                st.error(f"⚠️ Atenção: Isso excluirá permanentemente o veículo {selected_v_del}.")
                confirm_v = st.checkbox("Confirmo a exclusão definitiva do veículo.", key="confirm_v_del")
                if st.button("Excluir Veículo", type="primary", disabled=not confirm_v):
                    repo.delete("vehicles", v_data["id"])
                    st.success("Veículo excluído com sucesso!")
                    st.rerun()
                    
        with col_d2:
            st.markdown("##### Excluir Motorista")
            selected_d_del = st.selectbox("Selecione o motorista", [None] + list(drivers_map), key="del_d_select")
            if selected_d_del:
                d_data = drivers_map[selected_d_del]
                st.error(f"⚠️ Atenção: Isso excluirá permanentemente o motorista {selected_d_del}.")
                confirm_d = st.checkbox("Confirmo a exclusão definitiva do motorista.", key="confirm_d_del")
                if st.button("Excluir Motorista", type="primary", disabled=not confirm_d):
                    repo.delete("drivers", d_data["id"])
                    st.success("Motorista excluído com sucesso!")
                    st.rerun()

with tab_operations:
    st.subheader("Controle de Trânsito & Abastecimento")
    
    # Exibir veículos em trânsito no topo
    open_checkins = [item for item in checkins if not item.get("checkout_at")]
    if open_checkins:
        st.markdown("##### 🚨 Veículos Atualmente em Operação (Trânsito)")
        active_checkin_rows = []
        for item in open_checkins:
            v = next((vehicle for vehicle in vehicles if vehicle["id"] == item["vehicle_id"]), None)
            d = next((driver for driver in drivers if driver["id"] == item["driver_id"]), None)
            active_checkin_rows.append({
                "Veículo": vehicle_label(v) if v else "Desconhecido",
                "Motorista": d["name"] if d else "Desconhecido",
                "Saída": item.get("checkin_at"),
                "Odômetro Inicial (km)": f"{as_number(item.get('odometer_start')):,.0f}",
                "Observações": item.get("notes", "")
            })
        st.dataframe(pd.DataFrame(active_checkin_rows), use_container_width=True, hide_index=True)
        st.divider()

    st.markdown("##### Realizar Novas Operações")
    op_col1, op_col2 = st.columns(2)
    
    with op_col1:
        st.markdown("⛽ Registrar Abastecimento")
        if not vehicles:
            st.info("Cadastre veículos primeiro.")
        else:
            by_label_active = {vehicle_label(v): v for v in vehicles if v.get("status") != "Inativo"}
            with st.form("new_fuel_form", clear_on_submit=True):
                selected = st.selectbox("Veículo", list(by_label_active))
                liters = st.number_input("Litros", min_value=0.01, step=1.0)
                cost = st.number_input("Custo Total (R$)", min_value=0.01, step=1.0)
                odometer = st.number_input("Odômetro Atual", min_value=0.0, step=1.0)
                fuel_date = st.date_input("Data", value=date.today())
                if st.form_submit_button("Salvar Abastecimento"):
                    vehicle = by_label_active[selected]
                    if odometer < vehicle_odometer(vehicle["id"], fuel, maintenance, checkins):
                        st.error("O odômetro não pode ser menor que o último registro do veículo.")
                    else:
                        repo.add("fuel", {"vehicle_id": vehicle["id"], "liters": liters, "cost": cost, "fuel_date": fuel_date, "odometer": odometer})
                        st.success("Abastecimento registrado com sucesso!")
                        st.rerun()

    with op_col2:
        tab_flow_1, tab_flow_2 = st.tabs(["🔑 Abrir Check-in", "🏁 Finalizar Check-in"])
        
        with tab_flow_1:
            active_drivers = [driver for driver in drivers if driver.get("status") == "Ativo"]
            available_vehicles = [vehicle for vehicle in vehicles if vehicle.get("status") == "Disponível"]
            if not active_drivers or not available_vehicles:
                st.info("É necessário ter pelo menos um motorista ativo e um veículo disponível para abrir check-in.")
            else:
                vehicle_options = {vehicle_label(vehicle): vehicle for vehicle in available_vehicles}
                driver_options = {driver["name"]: driver for driver in active_drivers}
                with st.form("new_checkin_form", clear_on_submit=True):
                    selected_vehicle = st.selectbox("Veículo", list(vehicle_options), key="checkin_v")
                    selected_driver = st.selectbox("Motorista", list(driver_options), key="checkin_d")
                    start = st.number_input("Odômetro de Saída", min_value=0.0, step=1.0)
                    checkin_date = st.date_input("Data de Saída", value=date.today(), key="checkin_d_input")
                    notes = st.text_area("Observações")
                    if st.form_submit_button("Confirmar Saída"):
                        vehicle = vehicle_options[selected_vehicle]
                        if start < vehicle_odometer(vehicle["id"], fuel, maintenance, checkins):
                            st.error("O odômetro de saída não pode ser menor que o último registro.")
                        else:
                            repo.add("checkins", {
                                "vehicle_id": vehicle["id"],
                                "driver_id": driver_options[selected_driver]["id"],
                                "checkin_at": checkin_date,
                                "checkout_at": "",
                                "odometer_start": start,
                                "odometer_end": "",
                                "notes": notes.strip()
                            })
                            repo.update("vehicles", vehicle["id"], {"status": "Em uso"})
                            st.success("Check-in aberto!")
                            st.rerun()

        with tab_flow_2:
            if not open_checkins:
                st.info("Não há check-ins abertos para finalizar.")
            else:
                checkin_options = {
                    f"{vehicle_label(next(v for v in vehicles if v['id'] == item['vehicle_id']))} · Saída: {item['checkin_at']}": item
                    for item in open_checkins
                }
                with st.form("checkout_form", clear_on_submit=True):
                    selected_checkin = st.selectbox("Selecione a Viagem", list(checkin_options))
                    end = st.number_input("Odômetro de Retorno", min_value=0.0, step=1.0)
                    checkout_date = st.date_input("Data de Retorno", value=date.today(), key="checkout_d_input")
                    if st.form_submit_button("Confirmar Retorno"):
                        checkin = checkin_options[selected_checkin]
                        if end < as_number(checkin.get("odometer_start")):
                            st.error("O odômetro de chegada não pode ser menor que o de saída.")
                        else:
                            repo.update("checkins", checkin["id"], {"checkout_at": checkout_date, "odometer_end": end})
                            repo.update("vehicles", checkin["vehicle_id"], {"status": "Disponível"})
                            st.success("Check-in finalizado!")
                            st.rerun()

with tab_maintenance:
    st.subheader("Manutenções Preventivas e Corretivas")
    
    maint_col1, maint_col2 = st.columns([1, 2])
    
    with maint_col1:
        st.markdown("##### 🛠️ Registrar Nova Manutenção")
        if not vehicles:
            st.info("Cadastre veículos primeiro.")
        else:
            by_label_maint = {vehicle_label(v): v for v in vehicles if v.get("status") != "Inativo"}
            with st.form("new_maintenance_form", clear_on_submit=True):
                selected = st.selectbox("Veículo", list(by_label_maint), key="maint_v")
                maint_type = st.selectbox("Tipo de Manutenção", ["Preventiva", "Corretiva", "Preditiva", "Outros"])
                description = st.text_area("Serviço executado")
                cost = st.number_input("Custo (R$)", min_value=0.01, step=1.0)
                odometer = st.number_input("Odômetro Atual", min_value=0.0, step=1.0)
                maint_date = st.date_input("Data", value=date.today())
                if st.form_submit_button("Registrar Manutenção"):
                    vehicle = by_label_maint[selected]
                    if not description.strip():
                        st.error("Descreva o serviço executado.")
                    elif odometer < vehicle_odometer(vehicle["id"], fuel, maintenance, checkins):
                        st.error("O odômetro não pode ser menor que o último registro do veículo.")
                    else:
                        repo.add("maintenance", {
                            "vehicle_id": vehicle["id"],
                            "maint_type": maint_type,
                            "description": description.strip(),
                            "cost": cost,
                            "maint_date": maint_date,
                            "odometer": odometer
                        })
                        st.success("Manutenção registrada com sucesso!")
                        st.rerun()
                        
    with maint_col2:
        st.markdown("##### 📋 Histórico Recente de Serviços")
        if maintenance:
            df_maint = pd.DataFrame(maintenance)
            vehicles_dict = {v["id"]: vehicle_label(v) for v in vehicles}
            df_maint["Veículo"] = df_maint["vehicle_id"].map(vehicles_dict)
            
            df_maint_display = df_maint.copy()
            df_maint_display["cost"] = df_maint_display["cost"].map(lambda x: f"R$ {as_number(x):,.2f}")
            df_maint_display["odometer"] = df_maint_display["odometer"].map(lambda x: f"{as_number(x):,.0f} km")
            
            st.dataframe(
                df_maint_display[["maint_date", "Veículo", "maint_type", "description", "cost", "odometer"]].rename(columns={
                    "maint_date": "Data",
                    "maint_type": "Tipo",
                    "description": "Serviço",
                    "cost": "Custo",
                    "odometer": "Odômetro"
                }), 
                use_container_width=True, hide_index=True
            )
        else:
            st.info("Nenhuma manutenção registrada até o momento.")

with tab_reports:
    st.subheader("📑 Central de Relatórios com Filtros Dinâmicos")
    
    report_name = st.selectbox("Selecione a tabela de dados", ["vehicles", "maintenance", "fuel", "drivers", "checkins"])
    data = rows(report_name)
    
    if data:
        df_report = pd.DataFrame(data)
        
        st.markdown("##### 🔍 Filtrar Dados")
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        
        filtered_df = df_report.copy()
        
        if "vehicle_id" in df_report.columns and vehicles:
            v_dict = {v["id"]: vehicle_label(v) for v in vehicles}
            filtered_df["Nome Veículo"] = filtered_df["vehicle_id"].map(v_dict)
            with filter_col1:
                v_filter = st.selectbox("Filtrar por Veículo", ["Todos"] + list(v_dict.values()))
                if v_filter != "Todos":
                    filtered_df = filtered_df[filtered_df["Nome Veículo"] == v_filter]
                    
        date_col = next((c for c in ["maint_date", "fuel_date", "checkin_at", "created_at"] if c in df_report.columns), None)
        if date_col:
            with filter_col2:
                df_report[date_col] = pd.to_datetime(df_report[date_col], errors='coerce')
                start_d = st.date_input("Data Inicial", value=date(2026, 1, 1))
                end_d = st.date_input("Data Final", value=date.today())
                
                filtered_df[date_col] = pd.to_datetime(filtered_df[date_col], errors='coerce')
                filtered_df = filtered_df[
                    (filtered_df[date_col].dt.date >= start_d) & 
                    (filtered_df[date_col].dt.date <= end_d)
                ]
                filtered_df[date_col] = filtered_df[date_col].dt.strftime("%Y-%m-%d")
                
        cost_col = next((c for c in ["cost", "amount"] if c in df_report.columns), None)
        if cost_col:
            with filter_col3:
                max_val = float(df_report[cost_col].apply(as_number).max() or 10000.0)
                min_cost, max_cost = st.slider("Faixa de Custo (R$)", 0.0, max_val, (0.0, max_val))
                filtered_df = filtered_df[
                    (filtered_df[cost_col].apply(as_number) >= min_cost) & 
                    (filtered_df[cost_col].apply(as_number) <= max_cost)
                ]

        st.markdown("##### 📊 Resumo dos Resultados Filtrados")
        res_col1, res_col2 = st.columns(2)
        with res_col1:
            st.metric("Total de Registros Encontrados", len(filtered_df))
        with res_col2:
            if cost_col:
                total_sum = filtered_df[cost_col].apply(as_number).sum()
                st.metric("Custo Total Filtrado", f"R$ {total_sum:,.2f}")
                
        st.divider()
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
        
        csv_data = filtered_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📥 Baixar Relatório Filtrado (CSV)", 
            csv_data, 
            f"relatorio_filtrado_{report_name}.csv", 
            "text/csv"
        )
    else:
        st.info("Ainda não há dados cadastrados nessa categoria para gerar relatórios.")

with tab_ai:
    st.subheader("🤖 Analista de Manutenção Inteligente")
    st.caption("Parecer automatizado gerado por Inteligência Artificial (OpenAI) baseado em dados históricos reais.")
    
    api_key = secret("OPENAI_API_KEY")
    if not api_key:
        st.info("Para ativar o analista, insira uma chave de API válida no arquivo de secrets.")
    elif not vehicles:
        st.info("Cadastre um veículo e registre manutenções/abastecimentos para poder rodar a IA.")
    else:
        selected_ai = st.selectbox("Escolha o veículo para o Parecer Técnico", [vehicle_label(v) for v in vehicles], key="ai_select")
        vehicle = next(v for v in vehicles if vehicle_label(v) == selected_ai)
        
        if st.button("🚀 Gerar Parecer de IA", type="primary"):
            with st.spinner("Analisando padrões de quilometragem, custos e histórico de serviços..."):
                try:
                    answer = analyze_maintenance(
                        str(api_key), vehicle,
                        [m for m in maintenance if m.get("vehicle_id") == vehicle["id"]],
                        [f for f in fuel if f.get("vehicle_id") == vehicle["id"]],
                    )
                    
                    low_answer = answer.lower()
                    if "crítico" in low_answer or "critico" in low_answer:
                        st.markdown('<div class="alert-card-danger">🚨 **Risco Identificado:** A IA apontou pontos CRÍTICOS que exigem atenção urgente no veículo!</div>', unsafe_allow_html=True)
                    elif "atenção" in low_answer or "atencao" in low_answer:
                        st.markdown('<div class="alert-card-warning">⚠️ **Alerta:** A IA sugere monitoramento e ações preventivas em breve.</div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="alert-card-success">✔️ **Sem Riscos Imediatos:** A IA sugere apenas monitoramento regular.</div>', unsafe_allow_html=True)
                    
                    st.markdown("### 📋 Análise Detalhada")
                    st.markdown(answer)
                except Exception as e:
                    st.error(f"Erro ao gerar parecer técnico: {e}")
