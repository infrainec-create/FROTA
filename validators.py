import re
from datetime import date


VALID_VEHICLE_STATUS = {"Disponível", "Em uso", "Manutenção", "Inativo"}
VALID_DRIVER_STATUS = {"Ativo", "Inativo"}
VALID_FINE_STATUS = {"Pendente", "Pago", "Contestada"}


class ValidationError(ValueError):
    """Erro seguro para exibir ao usuário."""


def required(form, field, label=None):
    value = (form.get(field) or "").strip()
    if not value:
        raise ValidationError(f"{label or field} é obrigatório.")
    return value


def positive_number(form, field, label=None, allow_zero=False):
    raw = required(form, field, label)
    try:
        value = float(raw.replace(",", "."))
    except ValueError as exc:
        raise ValidationError(f"{label or field} deve ser um número válido.") from exc
    if value < 0 or (value == 0 and not allow_zero):
        raise ValidationError(f"{label or field} deve ser maior que zero.")
    return value


def valid_date(form, field, label=None):
    value = required(form, field, label)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{label or field} deve estar no formato AAAA-MM-DD.") from exc


def normalized_plate(value):
    plate = re.sub(r"[^A-Z0-9]", "", value.upper())
    if not re.fullmatch(r"[A-Z]{3}[0-9][A-Z0-9][0-9]{2}", plate):
        raise ValidationError("Placa inválida.")
    return plate


def normalized_cpf(value):
    cpf = re.sub(r"\D", "", value)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        raise ValidationError("CPF inválido.")
    total = sum(int(cpf[i]) * (10 - i) for i in range(9))
    digit = (total * 10 % 11) % 10
    total2 = sum(int(cpf[i]) * (11 - i) for i in range(10))
    digit2 = (total2 * 10 % 11) % 10
    if digit != int(cpf[9]) or digit2 != int(cpf[10]):
        raise ValidationError("CPF inválido.")
    return cpf


def secure_password(password):
    if len(password or "") < 12:
        raise ValidationError("A senha deve ter ao menos 12 caracteres.")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValidationError("A senha deve conter letras e números.")
    return password
