import secrets
from functools import wraps
from flask import abort, current_app, request, session


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def csrf_protect(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return view(*args, **kwargs)
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        session_token = session.get("csrf_token", "")
        if not token or not secrets.compare_digest(token, session_token):
            print(f"CSRF mismatch: request={token}, session={session_token}", flush=True)
            abort(400, "Token de segurança inválido. Atualize a página e tente novamente.")
        return view(*args, **kwargs)
    return wrapped


def configure_security(app):
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=app.config.get("SESSION_COOKIE_SECURE", not (app.config.get("TESTING", False) or app.debug)),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.after_request
    def headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        return response
