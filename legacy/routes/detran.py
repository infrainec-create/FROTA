import os
from flask import Blueprint, jsonify, request, session
from auth import login_required
from database import audit, get_db
from security import csrf_protect
from validators import ValidationError, positive_number, required, valid_date

detran_bp = Blueprint("detran", __name__)


@detran_bp.route("/api/detran/consult", methods=["POST"])
@login_required(role="admin")
@csrf_protect
def consult_detran():
    # A consulta só é habilitada quando a organização configurar um provedor homologado.
    provider_url = os.getenv("DETRAN_PROVIDER_URL")
    if not provider_url:
        return jsonify({"error": "Integração DETRAN não configurada. Defina DETRAN_PROVIDER_URL e credenciais do provedor homologado."}), 503
    return jsonify({"error": "Provedor configurado, mas o adaptador específico ainda deve ser implementado para a API contratada."}), 501


@detran_bp.route("/api/fines/import", methods=["POST"])
@login_required(role="admin")
@csrf_protect
def import_fine_api():
    data = request.get_json(silent=True) or {}
    try:
        driver_id = int(data.get("driver_id")); description = required(data, "description", "Descrição")
        amount = positive_number(data, "amount", "Valor"); fine_date = valid_date(data, "fine_date", "Data").isoformat()
        external_id = (data.get("external_id") or "").strip() or None
        db = get_db()
        if not db.execute("SELECT 1 FROM drivers WHERE id=?", (driver_id,)).fetchone(): raise ValidationError("Motorista inválido.")
        if external_id and db.execute("SELECT 1 FROM fines WHERE external_id=?", (external_id,)).fetchone():
            return jsonify({"error": "Esta multa já foi importada."}), 409
        cursor = db.execute("INSERT INTO fines (driver_id,description,amount,fine_date,status,external_id) VALUES (?, ?, ?, ?, 'Pendente', ?)", (driver_id, description, amount, fine_date, external_id))
        audit(db, "import", "fine", cursor.lastrowid, user_id=session["user_id"]); db.commit()
        return jsonify({"success": True, "status": "imported"})
    except (ValidationError, TypeError, ValueError):
        return jsonify({"error": "Dados inválidos para importação."}), 400
