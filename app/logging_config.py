"""
Central logging configuration (FIX 5).

Configures Flask's built-in `app.logger` with a rotating file handler so
auth events, CRUD operations, and errors are all persisted to
`logs/app.log` (created relative to the project root), in addition to
the console. Also exposes small helpers so routes don't each re-format
their own log lines (keeps FIX 5 and FIX 8 — clean code — consistent).
"""
import logging
import os
from logging.handlers import RotatingFileHandler


def configure_logging(app):
    log_dir = os.path.join(app.root_path, "..", "logs")
    log_dir = os.path.abspath(log_dir)
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "app.log")

    # Avoid attaching duplicate handlers if create_app() is called more
    # than once in the same process (e.g. in tests).
    already_configured = any(
        isinstance(h, RotatingFileHandler) and getattr(h, "_csu_handler", False)
        for h in app.logger.handlers
    )
    if already_configured:
        return

    handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3)
    handler._csu_handler = True
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    handler.setFormatter(formatter)
    handler.setLevel(logging.INFO)

    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    # Werkzeug's per-request access log is separate from app.logger;
    # keep it, but don't let it flood the file at DEBUG level.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def log_auth_event(action, username, success=True):
    """action: 'LOGIN' or 'LOGOUT'."""
    from flask import current_app

    # AUDIT FIX: logging must never break the main flow. This text log
    # line previously had no guard, unlike log_audit()/log_event() below
    # — a logger/handler failure (e.g. disk full) would have propagated
    # and turned a successful login into a 500 for the user.
    try:
        level = current_app.logger.info if success else current_app.logger.warning
        status = "success" if success else "failed"
        level(f"AUTH {action} {status}: user={username}")
    except Exception:
        pass  # the audit_logs row below is the durable record of this event

    # FEATURE 1 (audit logging): persist alongside the existing text log
    # line above (kept as-is for anyone tailing logs/app.log).
    # AUDIT FIX: guard this call too — log_audit() is already defensive
    # internally, but the caller must not depend on that; logging can
    # never be allowed to break the login flow from any layer.
    try:
        log_audit(f"AUTH_{action}", metadata={"username": username, "success": success})
    except Exception:
        try:
            current_app.logger.exception("audit_log_failed")
        except Exception:
            pass


def log_crud(action, entity_type, entity_id, username):
    """action: 'CREATE', 'UPDATE', or 'DELETE'."""
    from flask import current_app

    # AUDIT FIX: same "logging must never break the main flow" guard as
    # log_auth_event() above.
    try:
        current_app.logger.info(
            f"CRUD {action}: {entity_type} id={entity_id} by user={username}"
        )
    except Exception:
        pass

    # FEATURE 1 (audit logging): persist alongside the existing text log
    # line above.
    # AUDIT FIX: same defense-in-depth guard as log_auth_event() above.
    try:
        log_audit(
            f"{action}_{entity_type.upper()}",
            resource_type=entity_type,
            resource_id=entity_id,
            metadata={"username": username},
        )
    except Exception:
        try:
            current_app.logger.exception("audit_log_failed")
        except Exception:
            pass

    # FEATURE 4 (observability): structured, machine-parseable line in
    # addition to the human-readable one above.
    try:
        action_verb = {"CREATE": "created", "UPDATE": "updated", "DELETE": "deleted"}.get(
            action, action.lower()
        )
        entity_slug = "kb" if entity_type == "KnowledgeBase" else entity_type.lower()
        log_event(f"{entity_slug}_{action_verb}", resource_id=entity_id, username=username)
    except Exception:
        pass


def log_audit(action, resource_type=None, resource_id=None, metadata=None, user_id=None):
    """
    FEATURE 1 (enterprise): writes a row to the `audit_logs` table.

    Deliberately defensive — a failure to write an audit row (e.g. the
    table doesn't exist yet on a database that hasn't run migrations)
    must never break the request that triggered it. The error is logged
    to the normal app logger instead, and the exception is swallowed.

    `user_id` can be passed explicitly (e.g. for a failed login, where
    there is no authenticated `current_user`); otherwise it's inferred
    from `current_user` when available.
    """
    from flask import current_app
    from flask_login import current_user
    from app.extensions import db, safe_commit

    if user_id is None:
        try:
            user_id = current_user.id if current_user.is_authenticated else None
        except Exception:
            user_id = None

    try:
        from app.models.audit_log import AuditLog

        entry = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            event_metadata=metadata,
        )
        db.session.add(entry)
        safe_commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception(f"Failed to write audit log entry for action={action}")


def log_event(event, **fields):
    """
    FEATURE 4 (observability): structured (JSON) log line, e.g.:
        log_event("kb_created", user_id=3, kb_id=42)
    Written via app.logger (same handlers/rotation as everything else),
    but always valid JSON on one line — safe to grep/parse without
    depending on the plain-text formatter used elsewhere in this file.
    """
    import json
    from flask import current_app

    payload = {"event": event, **fields}
    try:
        current_app.logger.info(json.dumps(payload, default=str))
    except Exception:
        current_app.logger.info(f"event={event} fields={fields}")
