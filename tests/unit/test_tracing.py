from unittest.mock import MagicMock

from api.tracing import start_trace


def test_maps_onto_observation_api():
    client = MagicMock()
    root = client.start_observation.return_value
    child = root.start_observation.return_value

    trace = start_trace(client, name="rag_query", input={"question": "q"})
    span = trace.span(name="retrieval")
    span.end(output={"chunks": 3})
    trace.update(output={"answer": "a"})
    trace.end()

    client.start_observation.assert_called_once_with(
        name="rag_query", input={"question": "q"}
    )
    root.start_observation.assert_called_once_with(name="retrieval", input=None)
    child.update.assert_called_once_with(output={"chunks": 3})
    child.end.assert_called_once()
    root.update.assert_called_once_with(output={"answer": "a"})
    root.end.assert_called_once()


def test_missing_client_is_a_no_op():
    trace = start_trace(None, name="rag_query")
    trace.span(name="x").end(output=1)
    trace.update(level="ERROR")
    trace.end()


def test_sdk_errors_never_raise():
    client = MagicMock()
    client.start_observation.side_effect = RuntimeError("bad keys")
    trace = start_trace(client, name="rag_query")
    trace.span(name="x").end(output=1)
    trace.end()

    client = MagicMock()
    client.start_observation.return_value.update.side_effect = RuntimeError("network")
    start_trace(client, name="t").update(output=1)
