import logging

from engine.actions import _state_detection_support as support


def test_build_xml_match_index_logs_attribute_fallback(caplog):
    broken_xml = (
        '<hierarchy><node resource-id="com.demo:id/title" text="Hello" '
        'content-desc="World"'
    )

    with caplog.at_level(logging.DEBUG, logger=support.__name__):
        index = support.build_xml_match_index(broken_xml)

    assert index is not None
    assert "com.demo:id/title" in index["resource_ids"]
    assert "hello" in index["visible_values"]
    assert "world" in index["visible_values"]
    assert any(
        "xml match index parse failed, falling back to attribute scan" in record.message
        for record in caplog.records
    )


def test_extract_candidates_from_xml_logs_parse_failure(caplog):
    with caplog.at_level(logging.DEBUG, logger=support.__name__):
        candidates = support.extract_candidates_from_xml("<hierarchy><node", package="com.demo")

    assert candidates == []
    assert any("candidate extraction XML parse failed" in record.message for record in caplog.records)


def test_parse_bounds_logs_invalid_value(caplog):
    with caplog.at_level(logging.DEBUG, logger=support.__name__):
        bounds = support.parse_bounds("invalid-bounds")

    assert bounds == {"left": 0, "top": 0, "right": 0, "bottom": 0}
    assert any("failed to parse bounds" in record.message for record in caplog.records)
