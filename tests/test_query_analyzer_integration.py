"""Tests for wiring the structured analyzer to the shared Azure adapter."""

from types import SimpleNamespace
from unittest.mock import Mock

from app.rag.azure import AzureOpenAIAdapter
from app.rag.query_analysis import AzureQueryAnalyzer


def test_openai_adapter_exposes_shared_query_analyzer() -> None:
    client = Mock()
    adapter = AzureOpenAIAdapter(client, embedding_deployment="embed", chat_deployment="chat")

    analyzer = adapter.query_analyzer()

    assert isinstance(analyzer, AzureQueryAnalyzer)


def test_query_analyzer_network_failure_falls_back_without_exposing_error() -> None:
    client = Mock()
    client.chat.completions.create.side_effect = RuntimeError("provider secret")
    analyzer = AzureQueryAnalyzer(client, deployment="chat")

    result = analyzer.analyze("What is the limit?")

    assert result.ambiguous is True
    assert "provider secret" not in result.model_dump_json()


def test_query_analyzer_uses_structured_response_format() -> None:
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"standalone_query":"pricing","ambiguous":false,"clarification":null,"temporal_intent":"unspecified","subqueries":["pricing"],"resolved_from_context":false}'
                )
            )
        ]
    )
    AzureQueryAnalyzer(client, deployment="chat").analyze("pricing")

    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "chat"
    assert kwargs["temperature"] == 0
    assert kwargs["response_format"]["type"] == "json_schema"
