"""
Shared JSON response envelope for the API (CHECK 4 fix).

Every response from /api/* — success or failure, whether it originates in
api_routes.py, the login_required 401 handler, the global 404/500 handlers,
or the rate limiter's 429 — now uses the same shape:

    {"success": true/false, "data": ..., "error": null/string}

This makes API clients able to rely on one parsing path regardless of
which layer produced the response.
"""
from flask import jsonify


def api_response(success, data=None, error=None, status_code=200):
    body = {"success": success, "data": data, "error": error}
    response = jsonify(body)
    response.status_code = status_code
    return response


def api_success(data=None, status_code=200):
    return api_response(True, data=data, error=None, status_code=status_code)


def api_error(message, status_code=400):
    return api_response(False, data=None, error=message, status_code=status_code)
