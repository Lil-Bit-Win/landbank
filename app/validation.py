"""
Structured validation layer (FIX 2).

Replaces the old boolean-only `validate_*_data` helpers that used to live
in the service modules. Each function returns a list of human-readable
error strings (empty list = valid), so callers (web routes and the JSON
API) can surface every problem at once instead of one generic message.

Kept as plain functions rather than full Flask-WTF form classes so the
existing plain-HTML templates (kb_form.html, sop_form.html) did not need
to be restructured around WTForms field rendering — this preserves
template compatibility per the refactor's constraints.
"""
import re

MAX_TITLE_LEN = 200
MAX_TAGS_LEN = 255
MAX_TEXT_LEN = 5000
MAX_RESPONSIBLE_LEN = 150

# Letters, numbers, spaces, hyphens, underscores only, per tag.
_TAG_PATTERN = re.compile(r"^[A-Za-z0-9 _\-]+$")

# Strip control characters (except tab/newline) from user-supplied text
# before validating/storing it (FIX 7 — basic input sanitization).
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(value):
    if value is None:
        return ""
    return _CONTROL_CHARS.sub("", str(value)).strip()


def _check_required(value, label, errors):
    if not value:
        errors.append(f"{label} is required.")
        return False
    return True


def _check_max_length(value, label, max_len, errors):
    if len(value) > max_len:
        errors.append(f"{label} must be {max_len} characters or fewer.")


def validate_tags(tags, errors):
    if not tags:
        return
    if len(tags) > MAX_TAGS_LEN:
        errors.append(f"Tags must be {MAX_TAGS_LEN} characters or fewer.")
        return
    for raw_tag in tags.split(","):
        tag = raw_tag.strip()
        if tag and not _TAG_PATTERN.match(tag):
            errors.append(
                f"Tag '{tag}' is invalid — use only letters, numbers, spaces, - and _."
            )
            return


def validate_kb_input(data):
    """Returns a list of error strings; empty list means the input is valid."""
    errors = []

    title = sanitize_text(data.get("title"))
    description = description = sanitize_text(data.get("description"))
    category = sanitize_text(data.get("category"))
    problem = sanitize_text(data.get("problem"))
    solution = sanitize_text(data.get("solution"))
    tags = sanitize_text(data.get("tags"))

    if _check_required(title, "Title", errors):
        _check_max_length(title, "Title", MAX_TITLE_LEN, errors)

    if _check_required(description, "Description", errors):
        _check_max_length(description, "Description", MAX_TEXT_LEN, errors)

    _check_required(category, "Category", errors)

    if _check_required(problem, "Problem description", errors):
        _check_max_length(problem, "Problem description", MAX_TEXT_LEN, errors)

    if _check_required(solution, "Solution steps", errors):
        _check_max_length(solution, "Solution steps", MAX_TEXT_LEN, errors)

    validate_tags(tags, errors)

    return errors


def validate_sop_input(data):
    """Returns a list of error strings; empty list means the input is valid."""
    errors = []

    title = sanitize_text(data.get("title"))
    description = sanitize_text(data.get("description"))
    purpose = sanitize_text(data.get("purpose"))
    scope = sanitize_text(data.get("scope"))
    procedure = sanitize_text(data.get("procedure"))
    responsible_person = sanitize_text(data.get("responsible_person"))

    if _check_required(title, "Title", errors):
        _check_max_length(title, "Title", MAX_TITLE_LEN, errors)

    if _check_required(description, "Description", errors):
        _check_max_length(description, "Description", MAX_TEXT_LEN, errors)

    if _check_required(purpose, "Purpose", errors):
        _check_max_length(purpose, "Purpose", MAX_TEXT_LEN, errors)

    if _check_required(scope, "Scope", errors):
        _check_max_length(scope, "Scope", MAX_TEXT_LEN, errors)

    if _check_required(procedure, "Procedure", errors):
        _check_max_length(procedure, "Procedure", MAX_TEXT_LEN, errors)

    if _check_required(responsible_person, "Responsible person", errors):
        _check_max_length(responsible_person, "Responsible person", MAX_RESPONSIBLE_LEN, errors)

    return errors
