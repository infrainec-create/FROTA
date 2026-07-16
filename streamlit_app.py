from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
import hashlib
import os
import time
import urllib.parse
from typing import Any

import pandas as pd
import streamlit as st
import plotly.express as px

from drive_repository import DriveRepository
from maintenance_ai import analyze_maintenance


def apply_premium_chart_theme(fig):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Source Sans Pro, Inter, sans-serif"),
        xaxis=dict(gridcolor="rgba(128, 128, 128, 0.12)", zeroline=False),
        yaxis=dict(gridcolor="rgba(128, 128, 128, 0.12)", zeroline=False),
    )
    return fig


st.set_page_config(page_title="FrotaControl Pro", page_icon="🚚", layout="wide")


def secret(name: str, default: Any = None) -> Any:
    return st.secrets[name] if name in st.secrets else default


@st.cache_resource
def get_repository() -> DriveRepository:
    account = secret("gcp_service_account")
    folder_id = secret("google_drive_folder_id") or secret("google_sheet_id")
    return DriveRepository(
        dict(account) if account else None,
        str(folder_id) if folder_id else None
    )


repo = get_repository()

# Garantir que a instância em cache do repositório está atualizada
try:
    repo._validate_table("expenses")
except ValueError:
    st.cache_resource.clear()
    st.cache_data.clear()
    st.rerun()


# 🔒 Password Hashing Helper
def hash_password(password: str) -> str:
    salt = "frota_control_salt_2026_"
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


# 🚪 Advanced Authentication Gate
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "login_attempts" not in st.session_state:
    st.session_state["login_attempts"] = 0
if "lockout_time" not in st.session_state:
    st.session_state["lockout_time"] = 0.0

# Brute-Force lockout check (60 seconds block after 5 failed attempts)
if st.session_state["login_attempts"] >= 5:
    elapsed_lock = time.time() - st.session_state["lockout_time"]
    if elapsed_lock < 60:
        st.error(f"⚠️ Conta temporariamente bloqueada devido a muitas tentativas incorretas. Tente novamente em {int(60 - elapsed_lock)} segundos.")
        st.stop()
    else:
        st.session_state["login_attempts"] = 0

# Session Timeout check (30 minutes = 1800 seconds)
if st.session_state["authenticated"]:
    if "last_activity" in st.session_state:
        elapsed_act = time.time() - st.session_state["last_activity"]
        if elapsed_act > 1800:
            st.session_state["authenticated"] = False
            st.session_state["username"] = ""
            st.warning("⚠️ Sua sessão expirou por inatividade. Faça login novamente.")
            st.rerun()
    st.session_state["last_activity"] = time.time()

# Core CSS variables override for Theme configurations
DARK_THEME_CSS = """
    :root {
        --primary-color: #0052cc !important;
        --background-color: #0f172a !important;
        --secondary-background-color: #1e293b !important;
        --text-color: #f8fafc !important;

        --style-primary-color: #0052cc !important;
        --style-background-color: #0f172a !important;
        --style-secondary-background-color: #1e293b !important;
        --style-text-color: #f8fafc !important;
    }
"""

LIGHT_THEME_CSS = """
    :root {
        --primary-color: #0052cc !important;
        --background-color: #ffffff !important;
        --secondary-background-color: #f8fafc !important;
        --text-color: #0f172a !important;

        --style-primary-color: #0052cc !important;
        --style-background-color: #ffffff !important;
        --style-secondary-background-color: #f8fafc !important;
        --style-text-color: #0f172a !important;
    }
"""

if not st.session_state["authenticated"]:
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght=300;400;500;600;700&display=swap');
    html, body, [class*="css"] {{
        font-family: 'Plus Jakarta Sans', sans-serif;
    }}
    .login-box {{
        max-width: 480px;
        margin: 60px auto 20px auto;
        padding: 2.5rem;
        border-radius: 20px;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1);
        text-align: center;
    }}
    .login-title {{
        font-size: 1.8rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }}
    .login-subtitle {{
        font-size: 0.85rem;
        margin-bottom: 1.5rem;
    }}
    </style>
    """, unsafe_allow_html=True)

    
    st.markdown("""
    <div class="login-box">
        <div class="login-title">🚚 FrotaControl Pro</div>
        <div class="login-subtitle">Sistema Gerencial de Frotas</div>
    </div>
    """, unsafe_allow_html=True)

    try:
        users_list = repo.list("users")
    except Exception:
        users_list = []

    # Se não houver nenhum usuário, força a criação do primeiro administrador
    if not users_list:
        st.info("👋 Bem-vindo ao FrotaControl! Crie a primeira conta de administrador do sistema para começar.")
        with st.form("first_admin_form"):
            new_name = st.text_input("Nome Completo")
            new_user = st.text_input("Nome de Usuário (login)")
            new_pass = st.text_input("Senha", type="password")
            new_pass_confirm = st.text_input("Confirme a Senha", type="password")
            question = st.selectbox(
                "Pergunta de Segurança (para recuperar a senha no futuro)",
                [
                    "Qual o nome da sua mãe?",
                    "Qual o nome do seu primeiro animal de estimação?",
                    "Em qual cidade você nasceu?",
                    "Qual o modelo do seu primeiro carro?"
                ]
            )
            answer = st.text_input("Resposta de Segurança").strip().lower()
            
            if st.form_submit_button("Criar Conta Administrador", type="primary"):
                if not new_name.strip() or not new_user.strip() or not new_pass or not answer.strip():
                    st.error("Por favor, preencha todos os campos obrigatórios.")
                elif new_pass != new_pass_confirm:
                    st.error("As senhas informadas não coincidem.")
                else:
                    repo.add("users", {
                        "username": new_user.strip(),
                        "password": hash_password(new_pass),
                        "name": new_name.strip(),
                        "security_question": question,
                        "security_answer": answer
                    })
                    st.cache_data.clear()
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = new_user.strip()
                    st.session_state["login_attempts"] = 0
                    st.success("Administrador criado com sucesso!")
                    st.rerun()
        st.stop()

    col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
    with col_l2:
        auth_mode = st.tabs(["🔑 Entrar", "➕ Nova Conta", "🩹 Recuperar Acesso"])
        
        with auth_mode[0]:
            with st.form("login_form"):
                user = st.text_input("Usuário")
                passwd = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar", type="primary", use_container_width=True):
                    matched = next((u for u in users_list if u["username"] == user.strip()), None)
                    if matched and matched["password"] == hash_password(passwd):
                        st.session_state["authenticated"] = True
                        st.session_state["username"] = matched["username"]
                        st.session_state["login_attempts"] = 0
                        st.rerun()
                    else:
                        st.session_state["login_attempts"] += 1
                        if st.session_state["login_attempts"] >= 5:
                            st.session_state["lockout_time"] = time.time()
                            st.error("⚠️ Muitas tentativas incorretas. Conta bloqueada por 60 segundos.")
                            st.rerun()
                        else:
                            st.error(f"Usuário ou senha incorretos. Tentativa {st.session_state['login_attempts']}/5.")
                        
        with auth_mode[1]:
            st.caption("Cadastre novas contas de operadores ou administradores.")
            with st.form("register_form"):
                reg_code = st.text_input("Código de Convite (ACCESS_PASSWORD nos segredos)", type="password")
                reg_name = st.text_input("Nome Completo")
                reg_user = st.text_input("Nome de Usuário")
                reg_pass = st.text_input("Senha", type="password")
                reg_pass_confirm = st.text_input("Confirme a Senha", type="password")
                reg_question = st.selectbox(
                    "Pergunta de Segurança",
                    [
                        "Qual o nome da sua mãe?",
                        "Qual o nome do seu primeiro animal de estimação?",
                        "Em qual cidade você nasceu?",
                        "Qual o modelo do seu primeiro carro?"
                    ],
                    key="reg_q"
                )
                reg_answer = st.text_input("Resposta de Segurança", key="reg_a").strip().lower()
                
                if st.form_submit_button("Criar Conta", type="primary", use_container_width=True):
                    invite_code = secret("ACCESS_PASSWORD", "admin123")
                    if reg_code != invite_code:
                        st.error("Código de convite inválido.")
                    elif not reg_name.strip() or not reg_user.strip() or not reg_pass or not reg_answer.strip():
                        st.error("Preencha todos os campos obrigatórios.")
                    elif reg_pass != reg_pass_confirm:
                        st.error("As senhas informadas não coincidem.")
                    elif any(u["username"] == reg_user.strip() for u in users_list):
                        st.error("Este nome de usuário já está em uso.")
                    else:
                        repo.add("users", {
                            "username": reg_user.strip(),
                            "password": hash_password(reg_pass),
                            "name": reg_name.strip(),
                            "security_question": reg_question,
                            "security_answer": reg_answer
                        })
                        st.cache_data.clear()
                        st.success("Conta criada com sucesso! Faça login na aba 'Entrar'.")
                        
        with auth_mode[2]:
            st.caption("Redefina sua senha respondendo à sua pergunta de segurança.")
            rec_user = st.text_input("Seu Nome de Usuário", key="rec_u")
            
            matched_rec = None
            if rec_user:
                matched_rec = next((u for u in users_list if u["username"] == rec_user.strip()), None)
                if not matched_rec:
                    st.error("Usuário não cadastrado.")
            
            if matched_rec:
                st.info(f"Pergunta de Segurança: **{matched_rec.get('security_question')}**")
                with st.form("recovery_form"):
                    rec_answer = st.text_input("Sua Resposta", type="password")
                    new_pass_val = st.text_input("Nova Senha", type="password")
                    new_pass_confirm_val = st.text_input("Confirme a Nova Senha", type="password")
                    if st.form_submit_button("Redefinir Senha", type="primary", use_container_width=True):
                        if rec_answer.strip().lower() != matched_rec.get("security_answer", "").strip().lower():
                            st.error("Resposta de segurança incorreta.")
                        elif new_pass_val != new_pass_confirm_val:
                            st.error("As senhas informadas não coincidem.")
                        else:
                            repo.update("users", matched_rec["id"], {"password": hash_password(new_pass_val)})
                            st.cache_data.clear()
                            st.success("Senha redefinida com sucesso! Vá para a aba 'Entrar' para logar.")
    st.stop()


# Performance caching: avoids calling Google sheets API on every single component interaction
@st.cache_data(ttl=300)
def rows(table: str) -> list[dict[str, Any]]:
    return get_repository().list(table)


# Query Data Tables
users, vehicles, drivers, maintenance, fuel, checkins, fines, expenses = (rows(name) for name in ("users", "vehicles", "drivers", "maintenance", "fuel", "checkins", "fines", "expenses"))


# Sidebar Logout Button and Theme Selector
logged_username = st.session_state.get("username", "Administrador")
matched_logged = next((u for u in users if u["username"] == logged_username), None)
logged_name = matched_logged["name"] if matched_logged else logged_username

st.sidebar.markdown(f"### 👤 Logado como:")
st.sidebar.markdown(f"**{logged_name}**")
if st.sidebar.button("🚪 Sair do Sistema", use_container_width=True):
    st.session_state["authenticated"] = False
    st.session_state["username"] = ""
    st.rerun()

# Injected CSS based on Theme
theme_css = ""

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] {{
    font-family: 'Plus Jakarta Sans', sans-serif;
}}
{theme_css}
/* Card designs */
.kpi-card {{
    background: rgba(128, 128, 128, 0.05);
    border: 1px solid rgba(128, 128, 128, 0.15);
    border-radius: 16px;
    padding: 1.5rem;
    text-align: center;
    transition: all 0.3s ease;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    margin-bottom: 1rem;
}}
.kpi-card:hover {{
    transform: translateY(-2px);
    border-color: rgba(128, 128, 128, 0.25);
    background: rgba(128, 128, 128, 0.08);
}}
.kpi-title {{
    font-size: 0.85rem;
    color: #888888;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.5rem;
}}
.kpi-value {{
    font-size: 2.25rem;
    font-weight: 700;
}}
/* Alert cards */
.alert-card-warning {{
    background-color: rgba(245, 158, 11, 0.1);
    border-left: 4px solid #f59e0b;
    padding: 1rem;
    border-radius: 8px;
    color: #eab308;
    font-size: 0.9rem;
    margin-bottom: 0.8rem;
}}
.alert-card-success {{
    background-color: rgba(16, 185, 129, 0.1);
    border-left: 4px solid #10b981;
    padding: 1rem;
    border-radius: 8px;
    color: #10b981;
    font-size: 0.9rem;
    margin-bottom: 0.8rem;
}}
.alert-card-danger {{
    background-color: rgba(239, 68, 68, 0.1);
    border-left: 4px solid #ef4444;
    padding: 1rem;
    border-radius: 8px;
    color: #ef4444;
    font-size: 0.9rem;
    margin-bottom: 0.8rem;
}}
/* Alinha os botões principais para padrão premium */
.stButton>button {{
    border-radius: 12px;
    font-weight: 600;
    height: 3.2em;
    width: 100%;
    margin-top: 10px;
    transition: all 0.2s ease-in-out;
}}
.stButton>button:hover {{
    transform: translateY(-2px);
    box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
}}
</style>
""", unsafe_allow_html=True)


def as_number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        s = str(value).replace("R$", "").replace(" ", "").strip()
        if not s:
            return 0.0
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
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


# 📁 Audit Logger Helper
def log_action(action: str, details: str):
    try:
        repo.add("audit_log", {"action": action, "details": details})
    except Exception:
        pass


def safe_dataframe(data: list[dict[str, Any]], columns: list[str]) -> pd.DataFrame:
    if not data:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame(data)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df[columns]


# 📄 PDF Export Helper
def generate_pdf_report(table_name: str, df: pd.DataFrame) -> bytes:
    from fpdf import FPDF
    
    import unicodedata
    
    class PremiumPDF(FPDF):
        def header(self):
            self.set_font("helvetica", "B", 14)
            self.cell(0, 10, "FROTA CONTROL PRO - RELATORIO OPERACIONAL", ln=True, align="C")
            self.set_draw_color(37, 99, 235)  # blue line
            self.set_line_width(1)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(10)

        def footer(self):
            self.set_y(-15)
            self.set_font("helvetica", "I", 8)
            self.cell(0, 10, f"Pagina {self.page_no()}/{{nb}}", align="C")

    pdf = PremiumPDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 12)
    
    table_translations = {
        "vehicles": "Veículos",
        "maintenance": "Manutenção",
        "fuel": "Abastecimento",
        "drivers": "Motoristas",
        "checkins": "Check-ins",
        "fines": "Multas"
    }
    translated_table = table_translations.get(table_name, table_name)
    translated_table_clean = unicodedata.normalize("NFKD", translated_table).encode("ascii", "ignore").decode("ascii")
    
    pdf.cell(0, 10, f"Tabela de Origem: {translated_table_clean.upper()}", ln=True)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 5, f"Data de Emissao: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True)
    pdf.cell(0, 5, f"Total de Registros: {len(df)}", ln=True)
    pdf.ln(5)

    cols = list(df.columns)
    cols_to_show = [c for c in cols if c not in ["id", "vehicle_id", "driver_id", "created_at", "updated_at"]][:6]
    if not cols_to_show:
        cols_to_show = cols[:5]

    col_width = 190 / len(cols_to_show)

    # Table Header
    pdf.set_fill_color(37, 99, 235)  # primary blue
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", "B", 8)
    for col in cols_to_show:
        col_str = str(col).upper()
        col_str = unicodedata.normalize("NFKD", col_str).encode("ascii", "ignore").decode("ascii")
        pdf.cell(col_width, 8, col_str, border=1, fill=True, align="C")
    pdf.ln()

    # Table Rows
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", "", 8)
    
    fill = False
    for _, row in df.iterrows():
        if fill:
            pdf.set_fill_color(248, 250, 252)
        else:
            pdf.set_fill_color(255, 255, 255)
            
        for col in cols_to_show:
            val = str(row.get(col, ""))
            # Remove any special unicode chars to avoid FPDF character errors
            val = unicodedata.normalize("NFKD", val).encode("ascii", "ignore").decode("ascii")
            if len(val) > 25:
                val = val[:22] + "..."
            pdf.cell(col_width, 8, val, border=1, fill=True, align="C")
        pdf.ln()
        fill = not fill

    return bytes(pdf.output())


def generate_executive_pdf_report(
    period_label: str,
    kpis: dict[str, Any],
    metrics_list: list[dict[str, Any]],
    alerts_list: list[str],
    top_vehicles: list[dict[str, Any]]
) -> bytes:
    from fpdf import FPDF
    import unicodedata

    class ExecutivePDF(FPDF):
        def header(self):
            self.set_font("helvetica", "B", 14)
            self.cell(0, 10, "FROTA CONTROL PRO - RELATORIO GERENCIAL EXECUTIVO", ln=True, align="C")
            self.set_draw_color(0, 82, 204)
            self.set_line_width(1)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(10)

        def footer(self):
            self.set_y(-15)
            self.set_font("helvetica", "I", 8)
            self.cell(0, 10, f"Pagina {self.page_no()}/{{nb}}", align="C")

    pdf = ExecutivePDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    def norm(txt):
        return unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode("ascii")

    pdf.set_font("helvetica", "B", 11)
    pdf.cell(0, 8, f"PERIODO DE REFERENCIA: {norm(period_label).upper()}", ln=True)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 5, f"Data de Emissao: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True)
    pdf.ln(5)

    # 1. KPIs Financieros
    pdf.set_font("helvetica", "B", 10)
    pdf.set_fill_color(240, 242, 246)
    pdf.cell(0, 7, "1. RESUMO FINANCEIRO DA FROTA", ln=True, fill=True)
    pdf.ln(2)
    pdf.set_font("helvetica", "", 9)
    
    financials = [
        ("Abastecimento", f"R$ {kpis.get('fuel', 0.0):,.2f}"),
        ("Manutencao", f"R$ {kpis.get('maint', 0.0):,.2f}"),
        ("Multas e Infracoes", f"R$ {kpis.get('fines', 0.0):,.2f}"),
        ("Outras Despesas", f"R$ {kpis.get('expenses', 0.0):,.2f}"),
        ("CUSTO TOTAL DO PERIODO", f"R$ {kpis.get('total', 0.0):,.2f}")
    ]
    
    for label, val in financials:
        if "TOTAL" in label:
            pdf.set_font("helvetica", "B", 9)
        pdf.cell(100, 6, norm(label), border=1)
        pdf.cell(90, 6, val, border=1, ln=True, align="R")
        pdf.set_font("helvetica", "", 9)
    pdf.ln(6)

    # 2. Desempenho e Eficiência
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 7, "2. METRICAS DE DESEMPENHO E EFICIENCIA", ln=True, fill=True)
    pdf.ln(2)
    pdf.set_font("helvetica", "", 9)
    
    total_km = sum(as_number(m.get("km_raw")) for m in metrics_list)
    total_liters = sum(as_number(m.get("liters_raw")) for m in metrics_list)
    avg_kml = total_km / total_liters if total_liters > 0 else 0.0
    cost_per_km = kpis.get('total', 0.0) / total_km if total_km > 0 else 0.0
    
    eff_metrics = [
        ("Total de Veiculos Ativos", f"{kpis.get('active_vehicles', 0)} veiculos"),
        ("Kilometragem Total Rodada", f"{total_km:,.1f} km"),
        ("Litros de Combustivel Consumidos", f"{total_liters:,.1f} L"),
        ("Rendimento Medio da Frota", f"{avg_kml:.2f} km/L" if avg_kml > 0 else "N/A"),
        ("Custo Medio por KM Rodado", f"R$ {cost_per_km:.2f}/km" if cost_per_km > 0 else "N/A")
    ]
    
    for label, val in eff_metrics:
        pdf.cell(100, 6, norm(label), border=1)
        pdf.cell(90, 6, val, border=1, ln=True, align="R")
    pdf.ln(6)

    # 3. Top Veículos mais Caros
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 7, "3. VEICULOS COM MAIORES DESPESAS NO PERIODO", ln=True, fill=True)
    pdf.ln(2)
    pdf.set_font("helvetica", "B", 8)
    pdf.set_fill_color(0, 82, 204)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(100, 6, "VEICULO", border=1, fill=True)
    pdf.cell(90, 6, "GASTO TOTAL NO PERIODO", border=1, fill=True, ln=True, align="R")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", "", 9)
    
    top_5_sorted = sorted(top_vehicles, key=lambda x: x.get("Gasto Total", 0), reverse=True)[:5]
    for item in top_5_sorted:
        v_label = item.get("Veículo", "Desconhecido")
        v_cost = item.get("Gasto Total", 0.0)
        pdf.cell(100, 6, norm(v_label), border=1)
        pdf.cell(90, 6, f"R$ {v_cost:,.2f}", border=1, ln=True, align="R")
    pdf.ln(6)

    # 4. Alertas e Pendências Operacionais
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 7, "4. ALERTAS E PENDENCIAS OPERACIONAIS ATIVAS", ln=True, fill=True)
    pdf.ln(2)
    pdf.set_font("helvetica", "", 8)
    
    clean_alerts = []
    for a in alerts_list:
        clean_a = a.replace("**", "").replace("🔴", "[CRITICO]").replace("⚠️", "[ALERTA]").replace("🔧", "[MANUTENCAO]")
        clean_alerts.append(clean_a)
        
    if clean_alerts:
        for alert in clean_alerts[:15]:
            pdf.multi_cell(190, 5, f"- {norm(alert)}", border=0)
    else:
        pdf.set_font("helvetica", "", 9)
        pdf.cell(0, 6, "Nenhuma pendencia critica ou alerta de manutencao/documentacao ativo no periodo.", ln=True)
        
    pdf.ln(10)
    
    pdf.ln(15)
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(0, 5, "________________________________________________________", ln=True, align="C")
    pdf.cell(0, 5, "ASSINATURA DO GESTOR DA FROTA", ln=True, align="C")
    
    return bytes(pdf.output())


# Rest of streamlit app logic starts here...
st.caption("Gestão avançada de frotas com banco SQL de alta performance (SQLite / Google Drive Sync)")

if not (secret("gcp_service_account") and (secret("google_drive_folder_id") or secret("google_sheet_id"))):
    st.warning("⚠️ Executando com banco de dados SQLite local (`frota_drive.db`). Para sincronizar os dados no Google Drive, configure o arquivo `.streamlit/secrets.toml`.")

tab_dashboard, tab_vehicles, tab_operations, tab_maintenance, tab_fines, tab_expenses, tab_reports, tab_logs, tab_settings, tab_ai = st.tabs([
    "📊 Painel Geral", "👥 Veículos e Motoristas", "⚡ Operações Rápidas", "🔧 Manutenção", "🚨 Multas & Infrações", "💸 Outras Despesas", "📑 Relatórios & Filtros", "📁 Auditoria", "⚙️ Configurações", "🤖 Analista IA"
])

# Obtém limite de km configurado no banco de dados (padrão 10.000)
try:
    maint_limit_km = int(repo.get_config("maint_threshold", "10000"))
except AttributeError:
    st.cache_resource.clear()
    st.rerun()

with tab_dashboard:
    st.subheader("Indicadores de Desempenho (KPIs)")
    
    # 📆 FILTRO TEMPORAL NO DASHBOARD
    dash_col_f1, dash_col_f2 = st.columns(2)
    with dash_col_f1:
        selected_year = st.selectbox("Filtrar Ano", ["Todos"] + list(range(datetime.today().year - 2, datetime.today().year + 2)), key="dash_year")
    with dash_col_f2:
        months_map = {
            "Todos": None, "Janeiro": 1, "Fevereiro": 2, "Março": 3, "Abril": 4, "Maio": 5, "Junho": 6,
            "Julho": 7, "Agosto": 8, "Setembro": 9, "Outubro": 10, "Novembro": 11, "Dezembro": 12
        }
        selected_month_name = st.selectbox("Filtrar Mês", list(months_map.keys()), key="dash_month")
        selected_month = months_map[selected_month_name]
        
    # Filtra despesas com base no ano/mês selecionado
    filtered_maint = []
    for m in maintenance:
        d_str = m.get("maint_date") or m.get("created_at")
        if d_str:
            try:
                dt = datetime.strptime(d_str[:10], "%Y-%m-%d")
                if selected_year != "Todos" and dt.year != int(selected_year):
                    continue
                if selected_month is not None and dt.month != selected_month:
                    continue
            except ValueError:
                pass
        filtered_maint.append(m)
        
    filtered_fuel = []
    for f in fuel:
        d_str = f.get("fuel_date") or f.get("created_at")
        if d_str:
            try:
                dt = datetime.strptime(d_str[:10], "%Y-%m-%d")
                if selected_year != "Todos" and dt.year != int(selected_year):
                    continue
                if selected_month is not None and dt.month != selected_month:
                    continue
            except ValueError:
                pass
        filtered_fuel.append(f)
        
    filtered_fines = []
    for fi in fines:
        d_str = fi.get("fine_date") or fi.get("created_at")
        if d_str:
            try:
                dt = datetime.strptime(d_str[:10], "%Y-%m-%d")
                if selected_year != "Todos" and dt.year != int(selected_year):
                    continue
                if selected_month is not None and dt.month != selected_month:
                    continue
            except ValueError:
                pass
        filtered_fines.append(fi)

    filtered_expenses = []
    for e in expenses:
        d_str = e.get("expense_date") or e.get("created_at")
        if d_str:
            try:
                dt = datetime.strptime(d_str[:10], "%Y-%m-%d")
                if selected_year != "Todos" and dt.year != int(selected_year):
                    continue
                if selected_month is not None and dt.month != selected_month:
                    continue
            except ValueError:
                pass
        filtered_expenses.append(e)
    
    active = sum(v.get("status") == "Disponível" for v in vehicles)
    in_maintenance = sum(v.get("status") == "Manutenção" for v in vehicles)
    
    total_maint = sum(as_number(m.get("cost")) for m in filtered_maint)
    total_fuel = sum(as_number(f.get("cost")) for f in filtered_fuel)
    total_fines = sum(as_number(fi.get("amount")) for fi in filtered_fines)
    total_expenses = sum(as_number(e.get("cost")) for e in filtered_expenses)
    total_cost = total_maint + total_fuel + total_fines + total_expenses
    
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
            <div class="kpi-title">Custo no Período</div>
            <div class="kpi-value" style="color: #3b82f6;">R$ {total_cost:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("### 🔔 Alertas e Notificações (CNH, IPVA, Seguro e Manutenção)")
    alerts = []
    today = date.today()
    in_30_days = today + timedelta(days=30)
    
    # Vehicle Expiration & Maintenance Alerts using the custom threshold setting
    for vehicle in vehicles:
        current = vehicle_odometer(vehicle["id"], fuel, maintenance, checkins)
        history = [as_number(m.get("odometer")) for m in maintenance if m.get("vehicle_id") == vehicle["id"]]
        if current >= maint_limit_km and (not history or current - max(history) >= maint_limit_km):
            alerts.append(f"🔧 **Manutenção Preventiva**: {vehicle_label(vehicle)} necessita de revisão (limite: {maint_limit_km:,} km, odômetro atual: **{current:,.0f} km**).")
        
        # IPVA Alert
        ipva_str = vehicle.get("ipva_expiry")
        if ipva_str:
            try:
                ipva_dt = date.fromisoformat(ipva_str)
                if ipva_dt <= today:
                    alerts.append(f"🔴 **IPVA Vencido**: O IPVA do veículo **{vehicle_label(vehicle)}** venceu em {ipva_dt.strftime('%d/%m/%Y')}!")
                elif ipva_dt <= in_30_days:
                    alerts.append(f"⚠️ **IPVA Próximo do Vencimento**: O IPVA do veículo **{vehicle_label(vehicle)}** vence em {ipva_dt.strftime('%d/%m/%Y')}.")
            except ValueError:
                pass
                
        # Seguro Alert
        ins_str = vehicle.get("insurance_expiry")
        if ins_str:
            try:
                ins_dt = date.fromisoformat(ins_str)
                if ins_dt <= today:
                    alerts.append(f"🔴 **Seguro Vencido**: O seguro do veículo **{vehicle_label(vehicle)}** venceu em {ins_dt.strftime('%d/%m/%Y')}!")
                elif ins_dt <= in_30_days:
                    alerts.append(f"⚠️ **Seguro Próximo do Vencimento**: O seguro do veículo **{vehicle_label(vehicle)}** vence em {ins_dt.strftime('%d/%m/%Y')}.")
            except ValueError:
                pass

    # Driver CNH Alerts
    for driver in drivers:
        expiry_str = driver.get("license_expiry")
        if expiry_str:
            try:
                exp_dt = date.fromisoformat(expiry_str)
                if exp_dt <= today:
                    alerts.append(f"🔴 **CNH Vencida**: A CNH de **{driver['name']}** venceu em {exp_dt.strftime('%d/%m/%Y')}!")
                elif exp_dt <= in_30_days:
                    alerts.append(f"⚠️ **CNH Próxima do Vencimento**: A CNH de **{driver['name']}** vence em {exp_dt.strftime('%d/%m/%Y')}.")
            except ValueError:
                pass
    
    if alerts:
        for alert in alerts:
            card_class = "alert-card-danger" if "🔴" in alert else "alert-card-warning"
            st.markdown(f'<div class="{card_class}">{alert}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="alert-card-success">✔️ Todos os veículos e habilitações estão com a documentação e manutenção preventivas em dia!</div>', unsafe_allow_html=True)

    st.divider()

    # 📆 CRONOGRAMA MENSAL DE VENCIMENTOS (IPVA, Seguro e CNH no período selecionado)
    st.markdown(f"### 📅 Cronograma de Vencimentos ({selected_month_name} / {selected_year})")
    vencimentos_rows = []
    for vehicle in vehicles:
        ipva_str = vehicle.get("ipva_expiry")
        if ipva_str:
            try:
                dt = datetime.strptime(ipva_str[:10], "%Y-%m-%d")
                match_y = (selected_year == "Todos" or dt.year == int(selected_year))
                match_m = (selected_month is None or dt.month == selected_month)
                if match_y and match_m:
                    vencimentos_rows.append({
                        "Recurso": f"🚗 Veículo: {vehicle_label(vehicle)}",
                        "Tipo de Despesa/Conta": "IPVA",
                        "Data Limite": dt.strftime("%d/%m/%Y"),
                        "Status": "Vencido" if dt.date() < today else ("Atenção" if dt.date() <= in_30_days else "Em dia")
                    })
            except ValueError:
                pass
                
        ins_str = vehicle.get("insurance_expiry")
        if ins_str:
            try:
                dt = datetime.strptime(ins_str[:10], "%Y-%m-%d")
                match_y = (selected_year == "Todos" or dt.year == int(selected_year))
                match_m = (selected_month is None or dt.month == selected_month)
                if match_y and match_m:
                    vencimentos_rows.append({
                        "Recurso": f"🚗 Veículo: {vehicle_label(vehicle)}",
                        "Tipo de Despesa/Conta": "Seguro",
                        "Data Limite": dt.strftime("%d/%m/%Y"),
                        "Status": "Vencido" if dt.date() < today else ("Atenção" if dt.date() <= in_30_days else "Em dia")
                    })
            except ValueError:
                pass

    for driver in drivers:
        expiry_str = driver.get("license_expiry")
        if expiry_str:
            try:
                dt = datetime.strptime(expiry_str[:10], "%Y-%m-%d")
                match_y = (selected_year == "Todos" or dt.year == int(selected_year))
                match_m = (selected_month is None or dt.month == selected_month)
                if match_y and match_m:
                    vencimentos_rows.append({
                        "Recurso": f"👤 Motorista: {driver.get('name')}",
                        "Tipo de Despesa/Conta": "Vencimento CNH",
                        "Data Limite": dt.strftime("%d/%m/%Y"),
                        "Status": "Vencido" if dt.date() < today else ("Atenção" if dt.date() <= in_30_days else "Em dia")
                    })
            except ValueError:
                pass

    if vencimentos_rows:
        st.dataframe(pd.DataFrame(vencimentos_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum vencimento de IPVA, Seguro ou CNH agendado para o período selecionado.")

    st.divider()

    # 🚨 DETECTOR DE CONSUMO ANÔMALO
    st.markdown("### ⛽ Eficiência de Combustível & Detector de Desvio")
    fleet_kmls = []
    vehicle_kmls = {}
    for v in vehicles:
        v_fuel = [f for f in fuel if f.get("vehicle_id") == v["id"]]
        v_checkins = [c for c in checkins if c.get("vehicle_id") == v["id"]]
        odos = []
        for item in v_fuel:
            odos.append(as_number(item.get("odometer")))
        for item in v_checkins:
            odos.extend([as_number(item.get("odometer_start")), as_number(item.get("odometer_end"))])
        km_run = max(odos) - min(odos) if len(odos) >= 2 else 0.0
        liters = sum(as_number(f.get("liters")) for f in v_fuel)
        if liters > 0 and km_run > 0:
            kml = km_run / liters
            fleet_kmls.append(kml)
            vehicle_kmls[v["id"]] = kml
            
    fleet_avg_kml = sum(fleet_kmls) / len(fleet_kmls) if fleet_kmls else 0.0
    
    consumption_alerts = []
    if fleet_avg_kml > 0:
        for v in vehicles:
            v_kml = vehicle_kmls.get(v["id"], 0.0)
            if v_kml > 0 and v_kml < (0.8 * fleet_avg_kml):
                pct_diff = ((fleet_avg_kml - v_kml) / fleet_avg_kml) * 100
                consumption_alerts.append(
                    f"⚠️ **Rendimento Baixo / Consumo Excessivo**: O veículo **{vehicle_label(v)}** está com rendimento de **{v_kml:.2f} km/L** "
                    f"({pct_diff:.1f}% abaixo da média da frota de **{fleet_avg_kml:.2f} km/L**). Recomenda-se revisão mecânica ou vistoria."
                )

    if consumption_alerts:
        for c_alert in consumption_alerts:
            st.markdown(f'<div class="alert-card-warning">{c_alert}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="alert-card-success">✔️ Desempenho de consumo de todos os veículos está dentro do padrão esperado da frota!</div>', unsafe_allow_html=True)
        
    st.divider()
    
    # 📊 EFFICIENCY SUMMARY TABLE (stays all-time for cumulative accuracy)
    st.markdown("### 📊 Eficiência & Custos por Veículo (Histórico Acumulado)")
    metrics_rows = []
    for v in vehicles:
        v_id = v["id"]
        v_label = vehicle_label(v)
        
        v_fuel = [f for f in fuel if f.get("vehicle_id") == v_id]
        v_maint = [m for m in maintenance if m.get("vehicle_id") == v_id]
        v_checkins = [c for c in checkins if c.get("vehicle_id") == v_id]
        v_expenses = [e for e in expenses if e.get("vehicle_id") == v_id]
        
        odos = []
        for item in v_fuel + v_maint:
            odos.append(as_number(item.get("odometer")))
        for item in v_checkins:
            odos.extend([as_number(item.get("odometer_start")), as_number(item.get("odometer_end"))])
            
        km_run = max(odos) - min(odos) if len(odos) >= 2 else 0.0
        
        fuel_cost = sum(as_number(f.get("cost")) for f in v_fuel)
        maint_cost = sum(as_number(m.get("cost")) for m in v_maint)
        exp_cost = sum(as_number(e.get("cost")) for e in v_expenses)
        total_v_cost = fuel_cost + maint_cost + exp_cost
        
        liters = sum(as_number(f.get("liters")) for f in v_fuel)
        kml = km_run / liters if liters > 0 else 0.0
        cost_km = total_v_cost / km_run if km_run > 0 else 0.0
        
        metrics_rows.append({
            "Veículo": v_label,
            "KM Rodados": f"{km_run:,.0f} km",
            "Combustível": f"{liters:,.1f} L",
            "Média Consumo": f"{kml:.2f} km/L" if kml > 0 else "-",
            "Custo Total": f"R$ {total_v_cost:,.2f}",
            "Custo por KM": f"R$ {cost_km:.2f}/km" if cost_km > 0 else "-",
            "km_raw": km_run,
            "liters_raw": liters
        })
        
    if metrics_rows:
        st.dataframe(pd.DataFrame(metrics_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Dados insuficientes para calcular métricas de eficiência.")

    st.divider()

    # 📊 CUSTOM SEGMENTED COST BREAKDOWN PROGRESS BAR
    st.markdown("##### 📊 Distribuição Porcentual de Despesas da Frota no Período")
    total_c = total_fuel + total_maint + total_fines + total_expenses
    if total_c > 0:
        pct_fuel = (total_fuel / total_c) * 100
        pct_maint = (total_maint / total_c) * 100
        pct_fines = (total_fines / total_c) * 100
        pct_exp = (total_expenses / total_c) * 100
        
        st.markdown(f"""
        <div style="display: flex; height: 28px; border-radius: 14px; overflow: hidden; margin: 15px 0 10px 0; background: rgba(128,128,128,0.15); box-shadow: inset 0 2px 4px rgba(0,0,0,0.06);">
            {"".join([
                f'<div style="width: {pct_fuel}%; background: linear-gradient(135deg, #3b82f6, #2563eb); text-align: center; color: white; font-size: 11px; line-height: 28px; font-weight: 600;" title="Abastecimento: R$ {total_fuel:,.2f}">⛽ {pct_fuel:.1f}%</div>' if pct_fuel > 0 else '',
                f'<div style="width: {pct_maint}%; background: linear-gradient(135deg, #10b981, #059669); text-align: center; color: white; font-size: 11px; line-height: 28px; font-weight: 600;" title="Manutenção: R$ {total_maint:,.2f}">🔧 {pct_maint:.1f}%</div>' if pct_maint > 0 else '',
                f'<div style="width: {pct_fines}%; background: linear-gradient(135deg, #ef4444, #dc2626); text-align: center; color: white; font-size: 11px; line-height: 28px; font-weight: 600;" title="Multas: R$ {total_fines:,.2f}">🚨 {pct_fines:.1f}%</div>' if pct_fines > 0 else '',
                f'<div style="width: {pct_exp}%; background: linear-gradient(135deg, #a78bfa, #8b5cf6); text-align: center; color: white; font-size: 11px; line-height: 28px; font-weight: 600;" title="Outros: R$ {total_expenses:,.2f}">💸 {pct_exp:.1f}%</div>' if pct_exp > 0 else ''
            ])}
        </div>
        <div style="display: flex; justify-content: space-around; font-size: 0.85rem; color: var(--text-color); opacity: 0.8; margin-bottom: 20px; flex-wrap: wrap;">
            <div>🔵 Abastecimento: <b>R$ {total_fuel:,.2f}</b></div>
            <div>🟢 Manutenção: <b>R$ {total_maint:,.2f}</b></div>
            <div>🔴 Multas: <b>R$ {total_fines:,.2f}</b></div>
            <div>🟣 Outros: <b>R$ {total_expenses:,.2f}</b></div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("Ainda não há despesas registradas no período selecionado.")

    st.divider()

    # CHARTS SECTION
    st.subheader("Gráficos Analíticos")
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.markdown("##### ⛽ vs 🔧 Despesas Mensais por Categoria")
        costs_data = []
        for m in filtered_maint:
            cost_val = as_number(m.get("cost"))
            maint_date_str = m.get("maint_date")
            if maint_date_str:
                try:
                    month_str = datetime.strptime(maint_date_str[:10], "%Y-%m-%d").strftime("%Y-%m")
                    costs_data.append({"Mês": month_str, "Categoria": "Manutenção", "Valor": cost_val})
                except ValueError:
                    pass
        for f in filtered_fuel:
            cost_val = as_number(f.get("cost"))
            fuel_date_str = f.get("fuel_date")
            if fuel_date_str:
                try:
                    month_str = datetime.strptime(fuel_date_str[:10], "%Y-%m-%d").strftime("%Y-%m")
                    costs_data.append({"Mês": month_str, "Categoria": "Abastecimento", "Valor": cost_val})
                except ValueError:
                    pass
        for e in filtered_expenses:
            cost_val = as_number(e.get("cost"))
            expense_date_str = e.get("expense_date")
            if expense_date_str:
                try:
                    month_str = datetime.strptime(expense_date_str[:10], "%Y-%m-%d").strftime("%Y-%m")
                    costs_data.append({"Mês": month_str, "Categoria": "Outras Despesas", "Valor": cost_val})
                except ValueError:
                    pass
        if costs_data:
            df_costs = pd.DataFrame(costs_data)
            df_grouped = df_costs.groupby(["Mês", "Categoria"])["Valor"].sum().reset_index()
            fig = px.bar(
                df_grouped,
                x="Mês",
                y="Valor",
                color="Categoria",
                barmode="group",
                text_auto=".2s",
                labels={"Valor": "Custo (R$)"},
                color_discrete_map={
                    "Manutenção": "#10b981",
                    "Abastecimento": "#3b82f6",
                    "Outras Despesas": "#8b5cf6"
                }
            )
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=350)
            apply_premium_chart_theme(fig)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Ainda não há dados suficientes para gerar o gráfico de custos.")

    with chart_col2:
        st.markdown("##### 🚚 Status Atual da Frota")
        if vehicles:
            df_vehicles = pd.DataFrame(vehicles)
            status_counts = df_vehicles["status"].value_counts().reset_index()
            status_counts.columns = ["Status", "Quantidade"]
            fig_status = px.pie(
                status_counts,
                names="Status",
                values="Quantidade",
                hole=0.4,
                color="Status",
                color_discrete_map={
                    "Disponível": "#10b981",
                    "Manutenção": "#f59e0b",
                    "Em Uso": "#3b82f6",
                    "Inativo": "#ef4444"
                }
            )
            fig_status.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=350)
            apply_premium_chart_theme(fig_status)
            st.plotly_chart(fig_status, use_container_width=True)
        else:
            st.info("Cadastre veículos para ver o gráfico de status.")

    st.divider()
    st.subheader("Evolução & Análise de Custos")
    col_chart3, col_chart4 = st.columns(2)
    
    with col_chart3:
        st.markdown("##### 📈 Evolução de Gastos Mensais Totais")
        total_monthly_costs = {}
        for m in filtered_maint:
            cost_val = as_number(m.get("cost"))
            d_str = m.get("maint_date") or m.get("created_at")
            if d_str:
                try:
                    month_str = datetime.strptime(d_str[:10], "%Y-%m-%d").strftime("%Y-%m")
                    total_monthly_costs[month_str] = total_monthly_costs.get(month_str, 0) + cost_val
                except ValueError:
                    pass
        for f in filtered_fuel:
            cost_val = as_number(f.get("cost"))
            d_str = f.get("fuel_date") or f.get("created_at")
            if d_str:
                try:
                    month_str = datetime.strptime(d_str[:10], "%Y-%m-%d").strftime("%Y-%m")
                    total_monthly_costs[month_str] = total_monthly_costs.get(month_str, 0) + cost_val
                except ValueError:
                    pass
        for fi in filtered_fines:
            cost_val = as_number(fi.get("amount"))
            d_str = fi.get("fine_date") or fi.get("created_at")
            if d_str:
                try:
                    month_str = datetime.strptime(d_str[:10], "%Y-%m-%d").strftime("%Y-%m")
                    total_monthly_costs[month_str] = total_monthly_costs.get(month_str, 0) + cost_val
                except ValueError:
                    pass
        for e in filtered_expenses:
            cost_val = as_number(e.get("cost"))
            d_str = e.get("expense_date") or e.get("created_at")
            if d_str:
                try:
                    month_str = datetime.strptime(d_str[:10], "%Y-%m-%d").strftime("%Y-%m")
                    total_monthly_costs[month_str] = total_monthly_costs.get(month_str, 0) + cost_val
                except ValueError:
                    pass
                    
        if total_monthly_costs:
            df_evo = pd.DataFrame(list(total_monthly_costs.items()), columns=["Mês", "Custo Total (R$)"]).sort_values(by="Mês")
            fig_evo = px.line(
                df_evo,
                x="Mês",
                y="Custo Total (R$)",
                markers=True,
                labels={"Custo Total (R$)": "Total (R$)"}
            )
            fig_evo.update_traces(line=dict(color="#0052cc", width=3), marker=dict(size=8, color="#0052cc"))
            fig_evo.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=350)
            apply_premium_chart_theme(fig_evo)
            st.plotly_chart(fig_evo, use_container_width=True)
        else:
            st.info("Ainda não há dados suficientes para traçar a evolução de despesas.")

    with col_chart4:
        st.markdown("##### 🏆 Top 5 Veículos por Custo (Combustível + Manutenção + Despesas no Período)")
        v_costs = []
        for v in vehicles:
            v_id = v["id"]
            fuel_cost = sum(as_number(f.get("cost")) for f in filtered_fuel if f.get("vehicle_id") == v_id)
            maint_cost = sum(as_number(m.get("cost")) for m in filtered_maint if m.get("vehicle_id") == v_id)
            exp_cost = sum(as_number(e.get("cost")) for e in filtered_expenses if e.get("vehicle_id") == v_id)
            v_costs.append({"Veículo": vehicle_label(v), "Gasto Total": fuel_cost + maint_cost + exp_cost})
            
        if v_costs and any(item["Gasto Total"] > 0 for item in v_costs):
            df_v_costs = pd.DataFrame(v_costs).sort_values(by="Gasto Total", ascending=False).head(5)
            fig_v_costs = px.bar(
                df_v_costs,
                x="Veículo",
                y="Gasto Total",
                text_auto=".2s",
                color="Gasto Total",
                color_continuous_scale="Blues",
                labels={"Gasto Total": "Gasto (R$)"}
            )
            fig_v_costs.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=350, coloraxis_showscale=False)
            apply_premium_chart_theme(fig_v_costs)
            st.plotly_chart(fig_v_costs, use_container_width=True)
        else:
            st.info("Ainda não há gastos registrados para os veículos ativos no período.")

    # 📋 RELATÓRIO GERENCIAL EXECUTIVO PARA GESTORES
    st.divider()
    st.markdown("### 📋 Relatório Gerencial Executivo de Tomada de Decisão")
    st.caption("Gere e exporte um documento PDF consolidado contendo o resumo financeiro de despesas, métricas de eficiência de combustível, rankings de custos e todos os alertas operacionais do período selecionado para envio à diretoria e gestores.")
    
    period_label = f"{selected_month_name} / {selected_year}"
    kpis_pdf = {
        "fuel": total_fuel,
        "maint": total_maint,
        "fines": total_fines,
        "expenses": total_expenses,
        "total": total_cost,
        "active_vehicles": len(vehicles)
    }
    
    # Junta todos os alertas gerados no Dashboard
    all_current_alerts = alerts + (consumption_alerts if 'consumption_alerts' in locals() else [])
    
    try:
        pdf_exec_data = generate_executive_pdf_report(
            period_label=period_label,
            kpis=kpis_pdf,
            metrics_list=metrics_rows,
            alerts_list=all_current_alerts,
            top_vehicles=v_costs
        )
        
        st.download_button(
            label="📥 Gerar Relatório Executivo Consolidado (PDF)",
            data=pdf_exec_data,
            file_name=f"relatorio_gerencial_executivo_{selected_month_name.lower()}_{selected_year}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
    except Exception as e_exec_pdf:
        st.error(f"Erro ao preparar o relatório executivo: {e_exec_pdf}")

with tab_vehicles:
    st.subheader("Gerenciamento de Cadastro")
    
    v_tab_view, v_tab_docs, v_tab_create, v_tab_edit, v_tab_delete = st.tabs([
        "🔍 Visualizar Dados", "📋 Status de Documentos", "➕ Novo Cadastro", "✏️ Editar Registros", "❌ Excluir Registros"
    ])
    
    with v_tab_view:
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            st.markdown("##### Veículos Cadastrados")
            if vehicles:
                st.dataframe(safe_dataframe(vehicles, ["name", "plate", "year", "status", "ipva_expiry", "insurance_expiry"]), use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum veículo cadastrado.")
        with col_v2:
            st.markdown("##### Motoristas Cadastrados")
            if drivers:
                df_drivers_view = pd.DataFrame(drivers)
                open_checkins = [item for item in checkins if not item.get("checkout_at")]
                drivers_in_transit = {item["driver_id"] for item in open_checkins}
                
                def get_driver_status(row):
                    if row.get("status") == "Inativo":
                        return "Inativo"
                    if row.get("id") in drivers_in_transit:
                        return "Em viagem"
                    return "Disponível"
                
                df_drivers_view["Situação"] = df_drivers_view.apply(get_driver_status, axis=1)
                for col in ["name", "phone", "license", "license_expiry"]:
                    if col not in df_drivers_view.columns:
                        df_drivers_view[col] = ""
                        
                st.dataframe(df_drivers_view[["name", "phone", "license", "license_expiry", "Situação"]].rename(columns={
                    "name": "Nome",
                    "phone": "Telefone",
                    "license": "CNH",
                    "license_expiry": "Vencimento CNH"
                }), use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum motorista cadastrado.")

    with v_tab_docs:
        st.markdown("##### 📋 Controle Integrado de Vencimentos de Documentação")
        doc_rows = []
        today = date.today()
        in_30_days = today + timedelta(days=30)
        
        # Vehicles IPVA and Insurance
        for v in vehicles:
            ipva_str = v.get("ipva_expiry")
            if ipva_str:
                try:
                    ipva_dt = date.fromisoformat(ipva_str)
                    if ipva_dt <= today:
                        status = "🔴 Vencido"
                    elif ipva_dt <= in_30_days:
                        status = "🟡 Vence em breve"
                    else:
                        status = "🟢 Regular"
                    doc_rows.append({
                        "Entidade": f"🚗 Veículo: {vehicle_label(v)}",
                        "Documento": "IPVA",
                        "Vencimento": ipva_str,
                        "Status": status
                    })
                except ValueError:
                    pass
            ins_str = v.get("insurance_expiry")
            if ins_str:
                try:
                    ins_dt = date.fromisoformat(ins_str)
                    if ins_dt <= today:
                        status = "🔴 Vencido"
                    elif ins_dt <= in_30_days:
                        status = "🟡 Vence em breve"
                    else:
                        status = "🟢 Regular"
                    doc_rows.append({
                        "Entidade": f"🚗 Veículo: {vehicle_label(v)}",
                        "Documento": "Seguro Obrigatório",
                        "Vencimento": ins_str,
                        "Status": status
                    })
                except ValueError:
                    pass
                    
        # Drivers CNH
        for d in drivers:
            exp_str = d.get("license_expiry")
            if exp_str:
                try:
                    exp_dt = date.fromisoformat(exp_str)
                    if exp_dt <= today:
                        status = "🔴 Vencido"
                    elif exp_dt <= in_30_days:
                        status = "🟡 Vence em breve"
                    else:
                        status = "🟢 Regular"
                    doc_rows.append({
                        "Entidade": f"👤 Motorista: {d['name']}",
                        "Documento": "CNH",
                        "Vencimento": exp_str,
                        "Status": status
                    })
                except ValueError:
                    pass
                    
        if doc_rows:
            st.dataframe(pd.DataFrame(doc_rows), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma data de validade de IPVA, seguro ou CNH cadastrada.")
                
    with v_tab_create:
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.markdown("##### Cadastrar Veículo")
            with st.form("new_vehicle", clear_on_submit=True):
                name = st.text_input("Modelo / nome")
                plate = st.text_input("Placa").upper().strip()
                year = st.number_input("Ano", 1900, 2100, value=date.today().year)
                status = st.selectbox("Situação", ["Disponível", "Em uso", "Manutenção", "Inativo"])
                ipva_exp = st.date_input("Vencimento do IPVA (Opcional)", value=None)
                ins_exp = st.date_input("Vencimento do Seguro (Opcional)", value=None)
                if st.form_submit_button("Salvar veículo"):
                    if not name or not plate:
                        st.error("Informe nome e placa.")
                    elif any(v.get("plate") == plate for v in vehicles):
                        st.error("Esta placa já está cadastrada.")
                    else:
                        repo.add("vehicles", {
                            "name": name.strip(),
                            "plate": plate,
                            "year": year,
                            "status": status,
                            "ipva_expiry": ipva_exp.isoformat() if ipva_exp else "",
                            "insurance_expiry": ins_exp.isoformat() if ins_exp else ""
                        })
                        log_action("Cadastro de Veículo", f"Veículo {name} ({plate}) cadastrado.")
                        st.cache_data.clear()
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
                        log_action("Cadastro de Motorista", f"Motorista {d_name} cadastrado.")
                        st.cache_data.clear()
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
                
                ipva_curr = date.fromisoformat(v_data["ipva_expiry"]) if v_data.get("ipva_expiry") else None
                ins_curr = date.fromisoformat(v_data["insurance_expiry"]) if v_data.get("insurance_expiry") else None
                
                with st.form("form_edit_vehicle"):
                    edit_name = st.text_input("Modelo / nome", value=v_data.get("name", ""))
                    edit_plate = st.text_input("Placa", value=v_data.get("plate", "")).upper().strip()
                    edit_year = st.number_input("Ano", 1900, 2100, value=int(as_number(v_data.get("year")) or date.today().year))
                    edit_status = st.selectbox("Situação", ["Disponível", "Em uso", "Manutenção", "Inativo"], index=["Disponível", "Em uso", "Manutenção", "Inativo"].index(v_data.get("status", "Disponível")))
                    edit_ipva = st.date_input("Vencimento do IPVA", value=ipva_curr)
                    edit_ins = st.date_input("Vencimento do Seguro", value=ins_curr)
                    if st.form_submit_button("Salvar Alterações"):
                        repo.update("vehicles", v_data["id"], {
                            "name": edit_name.strip(),
                            "plate": edit_plate,
                            "year": edit_year,
                            "status": edit_status,
                            "ipva_expiry": edit_ipva.isoformat() if edit_ipva else "",
                            "insurance_expiry": edit_ins.isoformat() if edit_ins else ""
                        })
                        log_action("Edição de Veículo", f"Veículo {edit_name} ({edit_plate}) atualizado.")
                        st.cache_data.clear()
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
                        log_action("Edição de Motorista", f"Motorista {edit_d_name} atualizado.")
                        st.cache_data.clear()
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
                    log_action("Exclusão de Veículo", f"Veículo {selected_v_del} excluído.")
                    st.cache_data.clear()
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
                    log_action("Exclusão de Motorista", f"Motorista {selected_d_del} excluído.")
                    st.cache_data.clear()
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
            
            dest = item.get("destination", "").strip()
            map_link = ""
            if dest:
                map_link = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(dest)}"
                
            active_checkin_rows.append({
                "Veículo": vehicle_label(v) if v else "Desconhecido (Excluído)",
                "Motorista": d["name"] if d else "Desconhecido (Excluído)",
                "Saída": item.get("checkin_at"),
                "Destino": dest,
                "Mapa": map_link,
                "Odômetro Inicial": f"{as_number(item.get('odometer_start')):,.0f} km",
                "Observações": item.get("notes", "")
            })
            
        st.dataframe(
            pd.DataFrame(active_checkin_rows),
            column_config={
                "Mapa": st.column_config.LinkColumn("Mapa", help="Clique para ver o destino no Google Maps")
            },
            use_container_width=True, hide_index=True
        )
        st.divider()

    st.markdown("##### Realizar Novas Operações")
    op_col1, op_col2 = st.columns(2)
    
    with op_col1:
        st.markdown("⛽ Registrar Abastecimento")
        if not vehicles:
            st.info("Cadastre veículos primeiro.")
        else:
            by_label_active = {vehicle_label(v): v for v in vehicles if v.get("status") != "Inativo"}
            selected = st.selectbox("Veículo", list(by_label_active), key="fuel_v_select")
            liters = st.number_input("Litros", min_value=0.01, step=1.0, value=30.0, key="fuel_liters")
            cost = st.number_input("Custo Total (R$)", min_value=0.01, step=1.0, value=150.0, key="fuel_cost")
            odometer = st.number_input("Odômetro Atual", min_value=0.0, step=1.0, value=0.0, key="fuel_odo")
            fuel_date = st.date_input("Data", value=date.today(), key="fuel_date")

            vehicle = by_label_active[selected]
            last_odo = vehicle_odometer(vehicle["id"], fuel, maintenance, checkins)
            diff_odo = odometer - last_odo if odometer > last_odo else 0.0
            kml_calc = diff_odo / liters if liters > 0 else 0.0
            cost_per_liter = cost / liters if liters > 0 else 0.0

            st.markdown(f"""
            <div style="background: rgba(128,128,128,0.05); padding: 12px; border-radius: 8px; margin: 10px 0; border: 1px solid rgba(128,128,128,0.1);">
                📈 <b>Métricas Calculadas para o Abastecimento:</b><br/>
                • Consumo Médio do Ciclo: <b>{kml_calc:.2f} km/L</b> (KM Percorridos: {diff_odo:,.0f} km)<br/>
                • Preço por Litro: <b>R$ {cost_per_liter:.2f}/L</b>
            </div>
            """, unsafe_allow_html=True)

            # Prevenção de Abastecimentos Duplicados
            is_duplicate = any(
                f.get("vehicle_id") == vehicle["id"] and
                f.get("fuel_date") == str(fuel_date) and
                as_number(f.get("liters")) == liters and
                as_number(f.get("cost")) == cost
                for f in fuel
            )

            # Alerta Inteligente de Consumo Incomum
            is_abnormal = last_odo > 0 and diff_odo > 0 and (kml_calc < 3.0 or kml_calc > 28.0)
            confirm_save_abnormal = True
            if is_abnormal:
                st.warning(f"⚠️ **Consumo Incomum Detectado:** A média de consumo ({kml_calc:.2f} km/L) está fora dos padrões normais de operação (3 a 28 km/L). Por favor, certifique-se de que os litros e a quilometragem do painel estão corretos.")
                confirm_save_abnormal = st.checkbox("Confirmo que os dados de consumo incomum estão corretos e desejo salvar mesmo assim.", key="confirm_abnormal_fuel")

            if st.button("Salvar Abastecimento", type="primary", use_container_width=True):
                if odometer < last_odo:
                    st.error(f"Erro: O odômetro digitado é menor do que o último registro deste veículo ({last_odo:,.0f} km).")
                elif is_duplicate:
                    st.error("⚠️ **Aviso de Duplicidade:** Já existe um abastecimento idêntico registrado para este veículo na mesma data, com a mesma quantidade de litros e valor!")
                elif is_abnormal and not confirm_save_abnormal:
                    st.error("Erro: Marque a caixa de confirmação de consumo incomum para salvar.")
                else:
                    repo.add("fuel", {
                        "vehicle_id": vehicle["id"],
                        "liters": liters,
                        "cost": cost,
                        "fuel_date": fuel_date,
                        "odometer": odometer
                    })
                    log_action("Registro de Abastecimento", f"Abastecimento de {liters}L para {selected}. Consumo: {kml_calc:.2f} km/L.")
                    st.cache_data.clear()
                    st.success("Abastecimento salvo com sucesso!")
                    st.rerun()

    with op_col2:
        tab_flow_1, tab_flow_2, tab_flow_3 = st.tabs(["🔑 Abrir Check-in", "🏁 Finalizar Check-in", "📖 Histórico de Viagens"])
        
        with tab_flow_1:
            active_drivers = [driver for driver in drivers if driver.get("status") == "Ativo"]
            available_vehicles = [vehicle for vehicle in vehicles if vehicle.get("status") == "Disponível"]
            
            # Filtra motoristas em trânsito
            drivers_in_transit = {item["driver_id"] for item in open_checkins}
            available_drivers = [d for d in active_drivers if d["id"] not in drivers_in_transit]
            
            if not available_drivers or not available_vehicles:
                st.info("É necessário ter pelo menos um motorista ativo (e disponível) e um veículo disponível para abrir check-in.")
            else:
                vehicle_options = {vehicle_label(vehicle): vehicle for vehicle in available_vehicles}
                driver_options = {driver["name"]: driver for driver in available_drivers}
                with st.form("new_checkin_form", clear_on_submit=True):
                    selected_vehicle = st.selectbox("Veículo", list(vehicle_options), key="checkin_v")
                    selected_driver = st.selectbox("Motorista", list(driver_options), key="checkin_d")
                    destination = st.text_input("Destino / Cidade")
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
                                "destination": destination.strip(),
                                "notes": notes.strip()
                            })
                            repo.update("vehicles", vehicle["id"], {"status": "Em uso"})
                            log_action("Abertura de Check-in", f"Veículo {selected_vehicle} retirado por {selected_driver} com destino a {destination}.")
                            st.cache_data.clear()
                            st.success("Check-in aberto!")
                            st.rerun()

        with tab_flow_2:
            if not open_checkins:
                st.info("Não há check-ins abertos para finalizar.")
            else:
                checkin_options = {}
                for item in open_checkins:
                    v = next((veh for veh in vehicles if veh["id"] == item["vehicle_id"]), None)
                    v_label = vehicle_label(v) if v else f"Veículo {item['vehicle_id']} (Excluído)"
                    lbl = f"{v_label} · Saída: {item.get('checkin_at', '')}"
                    checkin_options[lbl] = item
                
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
                            log_action("Fechamento de Check-in", f"Check-in finalizado para veículo ID {checkin['vehicle_id']}.")
                            st.cache_data.clear()
                            st.success("Check-in finalizado!")
                            st.rerun()

        with tab_flow_3:
            st.markdown("##### 📖 Viagens Finalizadas (Histórico)")
            closed_checkins = [item for item in checkins if item.get("checkout_at")]
            if closed_checkins:
                closed_rows = []
                for item in closed_checkins:
                    v = next((veh for veh in vehicles if veh["id"] == item["vehicle_id"]), None)
                    d = next((driver for driver in drivers if driver["id"] == item["driver_id"]), None)
                    odo_start = as_number(item.get("odometer_start"))
                    odo_end = as_number(item.get("odometer_end"))
                    dist = odo_end - odo_start if odo_end >= odo_start else 0.0
                    
                    dest = item.get("destination", "").strip()
                    map_link = ""
                    if dest:
                        map_link = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(dest)}"

                    closed_rows.append({
                        "Veículo": vehicle_label(v) if v else "Veículo Excluído",
                        "Motorista": d["name"] if d else "Motorista Excluído",
                        "Saída": item.get("checkin_at"),
                        "Retorno": item.get("checkout_at"),
                        "Destino": dest,
                        "Mapa": map_link,
                        "Distância": f"{dist:,.0f} km",
                        "Notas": item.get("notes", "")
                    })
                st.dataframe(
                    pd.DataFrame(closed_rows),
                    column_config={
                        "Mapa": st.column_config.LinkColumn("Mapa", help="Clique para ver o destino no Google Maps")
                    },
                    use_container_width=True, hide_index=True
                )
            else:
                st.info("Nenhuma viagem finalizada encontrada no histórico.")

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
                        log_action("Registro de Manutenção", f"Serviço {maint_type} para {selected}. Custo: R$ {cost}.")
                        st.cache_data.clear()
                        st.success("Manutenção registrada com sucesso!")
                        st.rerun()
                        
    with maint_col2:
        st.markdown("##### 📋 Histórico Recente de Serviços")
        if maintenance:
            df_maint = safe_dataframe(maintenance, ["maint_date", "vehicle_id", "maint_type", "description", "cost", "odometer"])
            vehicles_dict = {v["id"]: vehicle_label(v) for v in vehicles}
            df_maint["Veículo"] = df_maint["vehicle_id"].map(vehicles_dict).fillna("Veículo Excluído")
            
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

with tab_fines:
    st.subheader("🚨 Controle de Multas & Infrações de Trânsito")
    
    fine_tab1, fine_tab2, fine_tab3 = st.tabs([
        "🔍 Visualizar Multas", "➕ Registrar Multa", "✏️ Gestão de Multas"
    ])
    
    with fine_tab1:
        if fines:
            df_fines_list = safe_dataframe(fines, ["fine_date", "driver_id", "description", "amount", "status"])
            drivers_dict = {d["id"]: d["name"] for d in drivers}
            df_fines_list["Motorista"] = df_fines_list["driver_id"].map(drivers_dict).fillna("Motorista Excluído")
            
            df_fines_disp = df_fines_list.copy()
            df_fines_disp["amount"] = df_fines_disp["amount"].map(lambda x: f"R$ {as_number(x):,.2f}")
            
            st.dataframe(
                df_fines_disp[["fine_date", "Motorista", "description", "amount", "status"]].rename(columns={
                    "fine_date": "Data Infração",
                    "description": "Descrição / Infração",
                    "amount": "Valor",
                    "status": "Situação"
                }), use_container_width=True, hide_index=True
            )
        else:
            st.info("Nenhuma multa registrada.")
            
    with fine_tab2:
        st.markdown("##### Cadastrar Nova Infração")
        active_drivers = [driver for driver in drivers if driver.get("status") == "Ativo"]
        if not active_drivers:
            st.info("Cadastre motoristas ativos primeiro.")
        else:
            driver_options = {driver["name"]: driver for driver in active_drivers}
            with st.form("new_fine_form", clear_on_submit=True):
                selected_driver = st.selectbox("Motorista Autuado", list(driver_options))
                fine_desc = st.text_area("Descrição da Infração")
                fine_amount = st.number_input("Valor da Autuação (R$)", min_value=0.01, step=1.0)
                fine_dt = st.date_input("Data da Infração", value=date.today())
                fine_status = st.selectbox("Situação da Multa", ["Pendente", "Pago", "Contestada"])
                if st.form_submit_button("Salvar Multa"):
                    repo.add("fines", {
                        "driver_id": driver_options[selected_driver]["id"],
                        "description": fine_desc.strip(),
                        "amount": fine_amount,
                        "fine_date": fine_dt,
                        "status": fine_status
                    })
                    log_action("Registro de Multa", f"Multa de R$ {fine_amount} para motorista {selected_driver}.")
                    st.cache_data.clear()
                    st.success("Multa registrada com sucesso!")
                    st.rerun()

    with fine_tab3:
        col_fe1, col_fe2 = st.columns(2)
        with col_fe1:
            st.markdown("##### Editar Multa")
            fines_map = {f"{f.get('fine_date')} · {f.get('description')[:30]}... · R$ {as_number(f.get('amount')):.2f}": f for f in fines}
            selected_fine_edit = st.selectbox("Selecione a Multa para editar", [None] + list(fines_map), key="edit_f_select")
            if selected_fine_edit:
                fine_data = fines_map[selected_fine_edit]
                d_curr = next((d for d in drivers if d["id"] == fine_data["driver_id"]), None)
                d_name_curr = d_curr["name"] if d_curr else ""
                driver_options = {driver["name"]: driver for driver in drivers}
                
                with st.form("form_edit_fine"):
                    edit_d = st.selectbox("Motorista Autuado", list(driver_options), index=list(driver_options).index(d_name_curr) if d_name_curr in driver_options else 0)
                    edit_desc = st.text_area("Descrição da Infração", value=fine_data.get("description", ""))
                    edit_amount = st.number_input("Valor (R$)", min_value=0.01, step=1.0, value=as_number(fine_data.get("amount")))
                    edit_date = st.date_input("Data da Infração", value=date.fromisoformat(fine_data["fine_date"]) if fine_data.get("fine_date") else date.today())
                    edit_status = st.selectbox("Situação da Multa", ["Pendente", "Pago", "Contestada"], index=["Pendente", "Pago", "Contestada"].index(fine_data.get("status", "Pendente")))
                    if st.form_submit_button("Salvar Alterações"):
                        repo.update("fines", fine_data["id"], {
                            "driver_id": driver_options[edit_d]["id"],
                            "description": edit_desc.strip(),
                            "amount": edit_amount,
                            "fine_date": edit_date,
                            "status": edit_status
                        })
                        log_action("Edição de Multa", f"Multa ID {fine_data['id']} atualizada.")
                        st.cache_data.clear()
                        st.success("Multa atualizada com sucesso!")
                        st.rerun()
                        
        with col_fe2:
            st.markdown("##### Excluir Multa")
            selected_fine_del = st.selectbox("Selecione a Multa para excluir", [None] + list(fines_map), key="del_f_select")
            if selected_fine_del:
                fine_data = fines_map[selected_fine_del]
                st.error(f"⚠️ Atenção: Isso excluirá permanentemente o registro desta multa.")
                confirm_f = st.checkbox("Confirmo a exclusão definitiva desta multa.", key="confirm_f_del")
                if st.button("Excluir Multa", type="primary", disabled=not confirm_f):
                    repo.delete("fines", fine_data["id"])
                    log_action("Exclusão de Multa", f"Multa ID {fine_data['id']} excluída.")
                    st.cache_data.clear()
                    st.success("Multa excluída com sucesso!")
                    st.rerun()

with tab_expenses:
    st.subheader("💸 Controle de Outras Despesas Operacionais")
    st.caption("Registre custos como pedágios, estacionamento, lavagens e outras taxas.")
    
    exp_tab1, exp_tab2, exp_tab3 = st.tabs([
        "🔍 Visualizar Despesas", "➕ Registrar Despesa", "✏️ Gestão de Despesas"
    ])
    
    with exp_tab1:
        if expenses:
            df_exp_list = safe_dataframe(expenses, ["expense_date", "vehicle_id", "expense_type", "cost", "description"])
            vehicles_dict = {v["id"]: vehicle_label(v) for v in vehicles}
            df_exp_list["Veículo"] = df_exp_list["vehicle_id"].map(vehicles_dict).fillna("Veículo Excluído")
            
            df_exp_disp = df_exp_list.copy()
            df_exp_disp["cost"] = df_exp_disp["cost"].map(lambda x: f"R$ {as_number(x):,.2f}")
            
            st.dataframe(
                df_exp_disp[["expense_date", "Veículo", "expense_type", "description", "cost"]].rename(columns={
                    "expense_date": "Data",
                    "expense_type": "Tipo de Despesa",
                    "description": "Descrição",
                    "cost": "Valor"
                }), use_container_width=True, hide_index=True
            )
        else:
            st.info("Nenhuma despesa registrada até o momento.")
            
    with exp_tab2:
        if not vehicles:
            st.info("Cadastre veículos primeiro.")
        else:
            by_label_exp = {vehicle_label(v): v for v in vehicles if v.get("status") != "Inativo"}
            with st.form("new_expense_form", clear_on_submit=True):
                selected_v = st.selectbox("Veículo", list(by_label_exp), key="exp_v_select")
                exp_type = st.selectbox("Tipo de Despesa", ["Pedágio", "Estacionamento", "Higienização / Lavagem", "Outros"])
                cost = st.number_input("Valor da Despesa (R$)", min_value=0.01, step=1.0, value=20.0)
                exp_date = st.date_input("Data da Despesa", value=date.today())
                desc = st.text_input("Descrição / Notas", placeholder="Ex: Pedágio Rodovia dos Bandeirantes")
                
                if st.form_submit_button("Registrar Despesa"):
                    v_item = by_label_exp[selected_v]
                    repo.add("expenses", {
                        "vehicle_id": v_item["id"],
                        "expense_type": exp_type,
                        "cost": cost,
                        "expense_date": exp_date,
                        "description": desc.strip()
                    })
                    log_action("Registro de Despesa", f"Despesa {exp_type} registrada para {selected_v}. Valor: R$ {cost}.")
                    st.cache_data.clear()
                    st.success("Despesa registrada com sucesso!")
                    st.rerun()
                    
    with exp_tab3:
        if not expenses:
            st.info("Nenhuma despesa registrada.")
        else:
            vehicles_dict = {v["id"]: vehicle_label(v) for v in vehicles}
            expenses_map = {}
            for e in expenses:
                v_lbl = vehicles_dict.get(e.get("vehicle_id"), "Desconhecido")
                label = f"{e.get('expense_date')} - {v_lbl} - {e.get('expense_type')} (R$ {as_number(e.get('cost')):.2f})"
                expenses_map[label] = e
                
            col_ex1, col_ex2 = st.columns(2)
            with col_ex1:
                st.markdown("##### Editar Despesa")
                selected_exp_edit = st.selectbox("Selecione a Despesa para editar", [None] + list(expenses_map), key="edit_exp_select")
                if selected_exp_edit:
                    exp_data = expenses_map[selected_exp_edit]
                    edit_v = next((v for v in vehicles if v["id"] == exp_data.get("vehicle_id")), None)
                    v_active_lbls = [vehicle_label(v) for v in vehicles if v.get("status") != "Inativo" or v["id"] == exp_data.get("vehicle_id")]
                    
                    edit_v_sel = st.selectbox("Veículo", v_active_lbls, index=v_active_lbls.index(vehicle_label(edit_v)) if edit_v else 0, key="edit_exp_v")
                    edit_type = st.selectbox("Tipo de Despesa", ["Pedágio", "Estacionamento", "Higienização / Lavagem", "Outros"], index=["Pedágio", "Estacionamento", "Higienização / Lavagem", "Outros"].index(exp_data.get("expense_type", "Pedágio")) if exp_data.get("expense_type") in ["Pedágio", "Estacionamento", "Higienização / Lavagem", "Outros"] else 0, key="edit_exp_type")
                    edit_cost = st.number_input("Valor da Despesa (R$)", min_value=0.01, step=1.0, value=float(as_number(exp_data.get("cost"))), key="edit_exp_cost")
                    
                    raw_date = exp_data.get("expense_date", "")
                    try:
                        parsed_date = date.fromisoformat(raw_date[:10])
                    except ValueError:
                        parsed_date = date.today()
                    edit_date = st.date_input("Data da Despesa", value=parsed_date, key="edit_exp_date")
                    edit_desc = st.text_input("Descrição / Notas", value=exp_data.get("description", ""), key="edit_exp_desc")
                    
                    if st.button("Salvar Alterações", key="save_exp_btn"):
                        by_label_active = {vehicle_label(v): v for v in vehicles}
                        selected_v_obj = by_label_active[edit_v_sel]
                        repo.update("expenses", exp_data["id"], {
                            "vehicle_id": selected_v_obj["id"],
                            "expense_type": edit_type,
                            "cost": edit_cost,
                            "expense_date": edit_date,
                            "description": edit_desc.strip()
                        })
                        log_action("Edição de Despesa", f"Despesa ID {exp_data['id']} atualizada.")
                        st.cache_data.clear()
                        st.success("Despesa atualizada com sucesso!")
                        st.rerun()
                        
            with col_ex2:
                st.markdown("##### Excluir Despesa")
                selected_exp_del = st.selectbox("Selecione a Despesa para excluir", [None] + list(expenses_map), key="del_exp_select")
                if selected_exp_del:
                    exp_data = expenses_map[selected_exp_del]
                    st.error("⚠️ Atenção: Isso excluirá permanentemente o registro desta despesa.")
                    confirm_e = st.checkbox("Confirmo a exclusão definitiva desta despesa.", key="confirm_exp_del")
                    if st.button("Excluir Despesa", type="primary", disabled=not confirm_e, key="del_exp_btn"):
                        repo.delete("expenses", exp_data["id"])
                        log_action("Exclusão de Despesa", f"Despesa ID {exp_data['id']} excluída.")
                        st.cache_data.clear()
                        st.success("Despesa excluída com sucesso!")
                        st.rerun()

with tab_reports:
    st.subheader("📑 Central de Relatórios com Filtros Dinâmicos")
    
    table_options = {
        "vehicles": "Veículos",
        "maintenance": "Manutenção",
        "fuel": "Abastecimento",
        "drivers": "Motoristas",
        "checkins": "Check-ins",
        "fines": "Multas",
        "expenses": "Outras Despesas"
    }
    report_name = st.selectbox(
        "Selecione a tabela de dados",
        options=list(table_options.keys()),
        format_func=lambda x: table_options[x]
    )
    data = rows(report_name)
    
    if data:
        df_report = pd.DataFrame(data)
        
        st.markdown("##### 🔍 Filtrar Relatório")
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        
        filtered_df = df_report.copy()
        
        if "vehicle_id" in df_report.columns and vehicles:
            v_dict = {v["id"]: vehicle_label(v) for v in vehicles}
            filtered_df["Nome Veículo"] = filtered_df["vehicle_id"].map(v_dict).fillna("Veículo Excluído")
            with filter_col1:
                v_filter = st.selectbox("Filtrar por Veículo", ["Todos"] + list(v_dict.values()))
                if v_filter != "Todos":
                    filtered_df = filtered_df[filtered_df["Nome Veículo"] == v_filter]
                    
        if "driver_id" in df_report.columns and drivers:
            d_dict = {d["id"]: d["name"] for d in drivers}
            filtered_df["Nome Motorista"] = filtered_df["driver_id"].map(d_dict).fillna("Motorista Excluído")
                    
        date_col = next((c for c in ["maint_date", "fuel_date", "checkin_at", "fine_date", "created_at"] if c in df_report.columns), None)
        if date_col:
            with filter_col2:
                preset = st.selectbox(
                    "Atalho de Período",
                    ["Personalizado", "Últimos 30 Dias", "Este Mês", "Este Ano", "Todo o Histórico"],
                    key="date_preset"
                )
                
                today_val = date.today()
                if preset == "Últimos 30 Dias":
                    default_start = today_val - timedelta(days=30)
                    default_end = today_val
                elif preset == "Este Mês":
                    default_start = date(today_val.year, today_val.month, 1)
                    default_end = today_val
                elif preset == "Este Ano":
                    default_start = date(today_val.year, 1, 1)
                    default_end = today_val
                elif preset == "Todo o Histórico":
                    default_start = date(2020, 1, 1)
                    default_end = today_val
                else:
                    default_start = date(2026, 1, 1)
                    default_end = today_val

                df_report[date_col] = pd.to_datetime(df_report[date_col], errors='coerce')
                start_d = st.date_input("Data Inicial", value=default_start)
                end_d = st.date_input("Data Final", value=default_end)
                
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
                
        # Preparação do DataFrame traduzido para visualização e exportação
        cols_to_drop = ["id", "vehicle_id", "driver_id", "created_at", "updated_at"]
        
        column_translations = {
            "name": "Nome",
            "plate": "Placa",
            "year": "Ano",
            "status": "Situação",
            "ipva_expiry": "Vencimento IPVA",
            "insurance_expiry": "Vencimento Seguro",
            "phone": "Telefone",
            "license": "CNH",
            "license_expiry": "Vencimento CNH",
            "maint_date": "Data da Manutenção",
            "maint_type": "Tipo de Manutenção",
            "description": "Descrição",
            "cost": "Custo (R$)",
            "odometer": "Odômetro",
            "liters": "Litros",
            "fuel_date": "Data do Abastecimento",
            "checkin_at": "Data Saída",
            "checkout_at": "Data Retorno",
            "odometer_start": "Odômetro Inicial",
            "odometer_end": "Odômetro Final",
            "destination": "Destino",
            "notes": "Observações",
            "fine_date": "Data da Infração",
            "amount": "Valor da Multa",
            "expense_type": "Tipo de Despesa",
            "expense_date": "Data da Despesa",
            "Nome Veículo": "Veículo",
            "Nome Motorista": "Motorista"
        }
        
        display_df = filtered_df.drop(columns=[c for c in cols_to_drop if c in filtered_df.columns], errors='ignore')
        display_df = display_df.rename(columns=column_translations)
        
        # Reordenar colunas para colocar Veículo e Motorista na frente, se existirem
        cols_order = []
        if "Veículo" in display_df.columns:
            cols_order.append("Veículo")
        if "Motorista" in display_df.columns:
            cols_order.append("Motorista")
        for c in display_df.columns:
            if c not in cols_order:
                cols_order.append(c)
        display_df = display_df[cols_order]

        st.divider()
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        down_col1, down_col2 = st.columns(2)
        with down_col1:
            csv_data = display_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "📥 Baixar Relatório (CSV)", 
                csv_data, 
                f"relatorio_filtrado_{report_name}.csv", 
                "text/csv",
                use_container_width=True
            )
        with down_col2:
            try:
                pdf_data = generate_pdf_report(report_name, display_df)
                st.download_button(
                    "📄 Baixar Relatório (PDF)", 
                    pdf_data, 
                    f"relatorio_filtrado_{report_name}.pdf", 
                    "application/pdf",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"Erro ao gerar PDF: {e}")
    else:
        st.info("Ainda não há dados cadastrados nessa categoria para gerar relatórios.")

with tab_logs:
    st.subheader("📁 Histórico de Auditoria do Sistema")
    st.caption("Logs das ações de cadastro, edição, exclusão e operação de trânsito em ordem cronológica.")
    
    logs_data = rows("audit_log")
    if logs_data:
        df_logs = pd.DataFrame(logs_data)
        
        # Filtros de busca na Auditoria
        col_log_f1, col_log_f2 = st.columns(2)
        with col_log_f1:
            search_query = st.text_input("🔍 Buscar nos Detalhes do Log", "")
        with col_log_f2:
            filter_action = st.selectbox("Filtrar por Tipo de Ação", ["Todos", "Cadastro", "Edição", "Exclusão", "Operação"])
            
        if "created_at" in df_logs.columns:
            df_logs["created_at"] = pd.to_datetime(df_logs["created_at"])
            df_logs = df_logs.sort_values(by="created_at", ascending=False)
            df_logs["created_at"] = df_logs["created_at"].dt.strftime("%Y-%m-%d %H:%M:%S")
            
        # Filtros aplicados
        filtered_logs = df_logs.copy()
        if search_query:
            filtered_logs = filtered_logs[
                filtered_logs["action"].str.contains(search_query, case=False, na=False) |
                filtered_logs["details"].str.contains(search_query, case=False, na=False)
            ]
            
        if filter_action != "Todos":
            if filter_action == "Cadastro":
                filtered_logs = filtered_logs[filtered_logs["action"].str.contains("cadastro|registro", case=False, na=False)]
            elif filter_action == "Edição":
                filtered_logs = filtered_logs[filtered_logs["action"].str.contains("edição|atualizado", case=False, na=False)]
            elif filter_action == "Exclusão":
                filtered_logs = filtered_logs[filtered_logs["action"].str.contains("exclusão|excluído|excluir", case=False, na=False)]
            elif filter_action == "Operação":
                filtered_logs = filtered_logs[filtered_logs["action"].str.contains("check-in|saída|retorno|abastecimento|manutenção|multa", case=False, na=False)]

        st.dataframe(
            filtered_logs[["created_at", "action", "details"]].rename(columns={
                "created_at": "Data/Hora",
                "action": "Ação Realizada",
                "details": "Detalhes"
            }), use_container_width=True, hide_index=True
        )
        
        # Export logs as CSV
        csv_logs = filtered_logs[["created_at", "action", "details"]].rename(columns={
            "created_at": "Data/Hora",
            "action": "Ação Realizada",
            "details": "Detalhes"
        }).to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="📥 Exportar Logs de Auditoria (CSV)",
            data=csv_logs,
            file_name=f"logs_auditoria_{datetime.today().strftime('%Y-%m-%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    else:
        st.info("Nenhum registro de auditoria disponível.")

with tab_settings:
    st.subheader("⚙️ Configurações Gerais do Sistema")
    st.caption("Ajuste as metas, limites e comportamentos operacionais do FrotaControl Pro.")
    
    st.markdown("##### 🔧 Limite de Revisão Preventiva")
    new_limit_km = st.number_input(
        "Frequência de Manutenção Preventiva (km)",
        min_value=1000,
        max_value=100000,
        value=maint_limit_km,
        step=1000,
        help="Ajuste o odômetro limite acumulado para alertas de preventiva dos veículos."
    )
    
    if st.button("Salvar Configurações", type="primary"):
        repo.set_config("maint_threshold", str(new_limit_km))
        st.cache_data.clear()
        st.success("Configurações atualizadas e sincronizadas no Google Drive!")
        st.rerun()

    st.divider()
    st.markdown("##### 💾 Backup do Banco de Dados")
    st.caption("Baixe uma cópia completa do arquivo de banco de dados SQLite local (`frota_drive.db`).")
    db_path = "frota_drive.db"
    if os.path.exists(db_path):
        try:
            with open(db_path, "rb") as f:
                db_bytes = f.read()
            st.download_button(
                label="📥 Baixar Banco de Dados Atual (SQLite)",
                data=db_bytes,
                file_name=f"backup_frota_{datetime.today().strftime('%Y-%m-%d')}.db",
                mime="application/x-sqlite3",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Erro ao ler banco de dados: {e}")
    else:
        st.info("Arquivo de banco de dados local não encontrado.")

    st.divider()
    st.markdown("##### 💾 Histórico de Backups Locais (Rotativos)")
    st.caption("O sistema mantém automaticamente os 5 backups locais mais recentes no disco do servidor para segurança contra falhas.")
    backup_dir = "backups"
    if os.path.exists(backup_dir):
        import glob
        local_backups = sorted(glob.glob(os.path.join(backup_dir, "frota_backup_*.db")), reverse=True)
        if local_backups:
            for i, b_path in enumerate(local_backups[:5]):
                b_name = os.path.basename(b_path)
                try:
                    b_size = os.path.getsize(b_path) / 1024
                    b_time = datetime.fromtimestamp(os.path.getmtime(b_path)).strftime('%d/%m/%Y %H:%M:%S')
                    
                    col_b1, col_b2 = st.columns([3, 1])
                    with col_b1:
                        st.markdown(f"📄 **{b_name}** ({b_size:.1f} KB)  \n*Gerado em: {b_time}*")
                    with col_b2:
                        with open(b_path, "rb") as f:
                            b_bytes = f.read()
                        st.download_button(
                            label="📥 Download",
                            data=b_bytes,
                            file_name=b_name,
                            mime="application/x-sqlite3",
                            key=f"dl_local_backup_{i}",
                            use_container_width=True
                        )
                except Exception:
                    pass
        else:
            st.info("Nenhum backup local rotativo gerado ainda. Ele será gerado na próxima alteração de dados.")
    else:
        st.info("Nenhum backup local rotativo gerado ainda. Ele será gerado na próxima alteração de dados.")

with tab_ai:
    st.subheader("🤖 Analista de Manutenção Inteligente")
    st.caption("Parecer automatizado gerado por Inteligência Artificial (OpenAI) baseado em dados históricos reais.")
    
    default_openai_key = secret("OPENAI_API_KEY") or ""
    default_gemini_key = secret("GEMINI_API_KEY") or ""
    
    ai_provider = st.selectbox(
        "🤖 Provedor de Inteligência Artificial",
        ["Google Gemini (Grátis / Flash)", "OpenAI GPT-4o-mini"],
        help="Selecione qual provedor de IA deseja usar. O Google Gemini possui uma cota de uso gratuita robusta."
    )
    
    if ai_provider == "Google Gemini (Grátis / Flash)":
        api_key = st.text_input("Chave de API do Gemini", type="password", value=default_gemini_key, placeholder="Cole sua API Key do Gemini (do Google AI Studio)")
        provider_val = "gemini"
    else:
        api_key = st.text_input("Chave de API do OpenAI", type="password", value=default_openai_key, placeholder="Cole sua API Key do OpenAI")
        provider_val = "openai"
        
    if not api_key:
        st.info(
            "Insira sua chave de API para habilitar o analista inteligente (ou configure-a nos secrets do Streamlit).\n\n"
            "💡 **Dica:** Você pode obter uma chave do Gemini 100% gratuita no Google AI Studio (https://aistudio.google.com/)."
        )
    elif not vehicles:
        st.info("Cadastre um veículo e registre manutenções/abastecimentos para poder rodar a IA.")
    else:
        options_ai = ["Toda a Frota (Consolidado)"] + [vehicle_label(v) for v in vehicles]
        selected_ai = st.selectbox("Escolha o veículo ou escopo para o Parecer Técnico", options_ai, key="ai_select")
        
        if selected_ai == "Toda a Frota (Consolidado)":
            vehicle = None
        else:
            vehicle = next((v for v in vehicles if vehicle_label(v) == selected_ai), None)
        
        ai_mode = st.radio("Selecione o Tipo de Análise da IA", ["Parecer Técnico Geral", "Previsão Orçamentária (Próximo Mês)"], horizontal=True)
        
        # We can run if vehicle is None (Toda a Frota) OR if single vehicle is selected
        run_ai = False
        if selected_ai == "Toda a Frota (Consolidado)" or vehicle is not None:
            run_ai = True
            
        if run_ai and st.button("🚀 Gerar Parecer de IA", type="primary"):
            with st.spinner("Analisando padrões de quilometragem, custos e histórico de serviços..."):
                try:
                    mode_val = "budget" if ai_mode == "Previsão Orçamentária (Próximo Mês)" else "general"
                    
                    if vehicle is None:
                        exp_list = expenses
                        maint_list = maintenance
                        fuel_list = fuel
                    else:
                        exp_list = [e for e in expenses if e.get("vehicle_id") == vehicle["id"]]
                        maint_list = [m for m in maintenance if m.get("vehicle_id") == vehicle["id"]]
                        fuel_list = [f for f in fuel if f.get("vehicle_id") == vehicle["id"]]
                        
                    answer = analyze_maintenance(
                        str(api_key), vehicle,
                        maint_list,
                        fuel_list,
                        mode=mode_val,
                        vehicles_list=vehicles,
                        expenses=exp_list,
                        provider=provider_val
                    )
                    
                    low_answer = answer.lower()
                    subject = "na frota" if vehicle is None else "no veículo"
                    if "critico" in low_answer or "crítico" in low_answer:
                        st.markdown(f'<div class="alert-card-danger">🚨 **Risco Identificado:** A IA apontou pontos CRÍTICOS que exigem atenção urgente {subject}!</div>', unsafe_allow_html=True)
                    elif "atencao" in low_answer or "atenção" in low_answer:
                        st.markdown(f'<div class="alert-card-warning">⚠️ **Alerta:** A IA sugere monitoramento e ações preventivas {subject} em breve.</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="alert-card-success">✔️ **Sem Riscos Imediatos:** A IA sugere apenas monitoramento regular {subject}.</div>', unsafe_allow_html=True)
                    
                    st.markdown("### 📋 Análise Detalhada")
                    st.markdown(answer)
                except Exception as e:
                    err_str = str(e)
                    if "insufficient_quota" in err_str or "quota" in err_str.lower() or "429" in err_str:
                        st.error(
                            "❌ **Cota da API do OpenAI Excedida:** A chave de API fornecida esgotou seus créditos ou atingiu o limite de faturamento.\n\n"
                            "**Como resolver:**\n"
                            "1. Acesse o painel financeiro da OpenAI (https://platform.openai.com/settings/organization/billing/overview) e faça uma recarga de créditos na sua conta.\n"
                            "2. Ou forneça uma nova chave de API ativa nas **Configurações** da aplicação."
                        )
                    else:
                        st.error(f"Erro ao gerar parecer técnico: {e}")
