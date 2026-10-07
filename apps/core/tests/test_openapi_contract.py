"""The OpenAPI schema must describe the error responses the API really returns
(found by Schemathesis status_code_conformance: D-17)."""

import pytest
from drf_spectacular.generators import SchemaGenerator

PUBLIC_DOCS = {"/api/schema/", "/api/docs/"}
UNAUTHENTICATED = {"/api/auth/signup/"}


@pytest.fixture(scope="module")
def schema():
    return SchemaGenerator().get_schema(request=None, public=True)


def _operations(schema):
    for path, ops in schema["paths"].items():
        if path in PUBLIC_DOCS:
            continue
        for method, op in ops.items():
            yield path, method, op["responses"]


def test_every_operation_documents_auth_and_throttle_errors(schema):
    missing = [
        (path, method, code)
        for path, method, responses in _operations(schema)
        for code in (["429"] if path in UNAUTHENTICATED else ["401", "403", "429"])
        if code not in responses
    ]
    assert missing == []


def test_write_operations_document_400(schema):
    missing = [
        (path, method)
        for path, method, responses in _operations(schema)
        if method in ("post", "put", "patch") and "400" not in responses
    ]
    assert missing == []


def test_detail_and_paginated_operations_document_404(schema):
    missing = [
        (path, method)
        for path, method, responses in _operations(schema)
        if ("{id}" in path or (method == "get" and "results" in str(responses.get("200"))))
        and "404" not in responses
    ]
    assert missing == []


def test_member_changes_document_409(schema):
    responses = schema["paths"]["/api/members/{id}/"]
    assert "409" in responses["patch"]["responses"]
    assert "409" in responses["delete"]["responses"]


def test_error_schema_component_exists(schema):
    assert "Error" in schema["components"]["schemas"]
