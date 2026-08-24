from civil_copilot.observability.tracing import TracingBundle, redact_trace_payload


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


def test_tracing_bundle_exposes_only_its_shared_langchain_callback():
    callback = object()

    assert TracingBundle(enabled=False).callbacks() == ()
    assert TracingBundle(enabled=True, callback_handler=callback).callbacks() == (callback,)


def test_langfuse_run_reference_uses_client_trace_id_and_real_client_url():
    class Span:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Client:
        trace_context = None

        def create_trace_id(self):
            return "actual-langfuse-trace-id"

        def get_trace_url(self, *, trace_id):
            assert trace_id == "actual-langfuse-trace-id"
            return "https://langfuse.example/project/demo/traces/actual-langfuse-trace-id"

        def start_as_current_span(self, *, trace_context, **_kwargs):
            self.trace_context = trace_context
            return Span()

    client = Client()
    bundle = TracingBundle(
        enabled=True,
        client=client,
        callback_factory=lambda trace_context: ("callback", trace_context),
    )

    with bundle.run("orchestrator", {"question": "safe"}) as run:
        assert run.callbacks == (("callback", {"trace_id": "actual-langfuse-trace-id"}),)
        assert run.reference.provider == "langfuse"
        assert run.reference.trace_id == "actual-langfuse-trace-id"
        assert run.reference.url == (
            "https://langfuse.example/project/demo/traces/actual-langfuse-trace-id"
        )

    assert client.trace_context == {"trace_id": "actual-langfuse-trace-id"}
