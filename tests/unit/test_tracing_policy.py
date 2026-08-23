from civil_copilot.observability.tracing import redact_trace_payload


def test_trace_redaction_removes_secrets_and_truncates_restricted_documents():
    payload = {
        "openai_api_key": "sk-secret-value",
        "authorization": "Bearer private-token",
        "nested": {"password": "database-password", "question": "safe question"},
        "document_text": "x" * 3000,
        "record_id": "RFI-087",
    }

    redacted = redact_trace_payload(payload, max_text_length=120)

    assert redacted["openai_api_key"] == "[REDACTED]"
    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["nested"]["password"] == "[REDACTED]"
    assert redacted["nested"]["question"] == "safe question"
    assert len(redacted["document_text"]) <= 140
    assert redacted["record_id"] == "RFI-087"


def test_trace_redaction_accepts_langfuse_keyword_callback_contract():
    redacted = redact_trace_payload(data={"secret_key": "private", "record_id": "RFI-087"})

    assert redacted == {"secret_key": "[REDACTED]", "record_id": "RFI-087"}
