import logging

from engine.actions import _state_detection_support as support


def test_build_xml_match_index_logs_attribute_fallback(caplog):
    broken_xml = (
        '<hierarchy><node resource-id="com.demo:id/title" text="Hello" content-desc="World"'
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
    assert any(
        "candidate extraction XML parse failed" in record.message for record in caplog.records
    )


def test_parse_bounds_logs_invalid_value(caplog):
    with caplog.at_level(logging.DEBUG, logger=support.__name__):
        bounds = support.parse_bounds("invalid-bounds")

    assert bounds == {"left": 0, "top": 0, "right": 0, "bottom": 0}
    assert any("failed to parse bounds" in record.message for record in caplog.records)


def test_extract_last_dm_message_direction_and_latest_match():
    xml = """
    <hierarchy>
      <node package="com.demo" text="Alice: hi" bounds="[10,100][200,180]" />
      <node package="com.demo" content-desc="Alice: latest" bounds="[20,300][220,380]" />
      <node package="com.demo" text="Me: outbound" bounds="[700,350][980,430]" />
      <node package="com.demo" text="Me: newest outbound" bounds="[710,500][990,580]" />
    </hierarchy>
    """

    inbound = support.extract_last_dm_message_from_xml(
        xml,
        package="com.demo",
        max_left=540,
        separator_tokens=["Alice:", "Me:"],
    )
    outbound = support.extract_last_outbound_dm_message_from_xml(
        xml,
        package="com.demo",
        min_left=540,
        separator_tokens=["Alice:", "Me:"],
    )

    assert inbound is not None
    assert inbound["message"] == "latest"
    assert inbound["center_y"] == 340

    assert outbound is not None
    assert outbound["message"] == "newest outbound"
    assert outbound["center_y"] == 540


def test_extract_last_dm_message_logs_parse_failure(caplog):
    with caplog.at_level(logging.DEBUG, logger=support.__name__):
        inbound = support.extract_last_dm_message_from_xml(
            "<hierarchy><node",
            package="com.demo",
            separator_tokens=["Alice:"],
        )
        outbound = support.extract_last_outbound_dm_message_from_xml(
            "<hierarchy><node",
            package="com.demo",
            separator_tokens=["Me:"],
        )

    assert inbound is None
    assert outbound is None
    assert any("inbound dm XML parse failed" in record.message for record in caplog.records)
    assert any("outbound dm XML parse failed" in record.message for record in caplog.records)


def test_extract_follow_and_unread_targets_from_xml():
    xml = """
    <hierarchy>
      <node package="com.demo" text="Follow" bounds="[100,360][220,440]" />
      <node package="com.demo" text="Follow" bounds="[100,360][220,440]" />
      <node package="com.demo" text="Follow" bounds="[100,120][220,180]" />
      <node package="com.demo" text="Unread" content-desc="2 unread messages" bounds="[50,280][300,360]" />
      <node package="com.demo" text="Message" content-desc="5 unread messages" bounds="[60,420][320,500]" />
    </hierarchy>
    """

    follow_targets = support.extract_follow_targets_from_xml(
        xml,
        package="com.demo",
        min_top=350,
        button_texts=["Follow"],
    )
    unread_targets = support.extract_unread_dm_targets_from_xml(
        xml,
        package="com.demo",
        min_top=250,
        markers=["unread"],
    )

    assert follow_targets == [
        {
            "text": "Follow",
            "bound": {"left": 100, "top": 360, "right": 220, "bottom": 440},
            "center": {"x": 160, "y": 400},
        }
    ]
    assert unread_targets == [
        {
            "text": "Unread",
            "desc": "2 unread messages",
            "bound": {"left": 50, "top": 280, "right": 300, "bottom": 360},
            "center": {"x": 175, "y": 320},
        },
        {
            "text": "Message",
            "desc": "5 unread messages",
            "bound": {"left": 60, "top": 420, "right": 320, "bottom": 500},
            "center": {"x": 190, "y": 460},
        },
    ]


def test_dm_and_follow_extractors_keep_empty_and_target_package_nodes_only():
    xml = """
    <hierarchy>
      <node package="com.other" text="Alice: wrong package" bounds="[10,320][240,400]" />
      <node package="" text="Alice: empty package latest" bounds="[20,480][260,560]" />
      <node package="com.demo" text="Alice: target package older" bounds="[30,420][270,500]" />
      <node package="com.other" text="Follow" bounds="[100,600][220,680]" />
      <node package="" text="Follow" bounds="[120,700][240,780]" />
      <node package="com.demo" text="Follow" bounds="[140,820][260,900]" />
    </hierarchy>
    """

    inbound = support.extract_last_dm_message_from_xml(
        xml,
        package="com.demo",
        max_left=540,
        separator_tokens=["Alice:"],
    )
    follow_targets = support.extract_follow_targets_from_xml(
        xml,
        package="com.demo",
        min_top=350,
        button_texts=["Follow"],
    )

    assert inbound is not None
    assert inbound["message"] == "empty package latest"
    assert inbound["bound"] == {"left": 20, "top": 480, "right": 260, "bottom": 560}

    assert follow_targets == [
        {
            "text": "Follow",
            "bound": {"left": 120, "top": 700, "right": 240, "bottom": 780},
            "center": {"x": 180, "y": 740},
        },
        {
            "text": "Follow",
            "bound": {"left": 140, "top": 820, "right": 260, "bottom": 900},
            "center": {"x": 200, "y": 860},
        },
    ]


def test_extract_follow_and_unread_targets_log_parse_failure(caplog):
    with caplog.at_level(logging.DEBUG, logger=support.__name__):
        follow_targets = support.extract_follow_targets_from_xml(
            "<hierarchy><node",
            package="com.demo",
            button_texts=["Follow"],
        )
        unread_targets = support.extract_unread_dm_targets_from_xml(
            "<hierarchy><node",
            package="com.demo",
            markers=["unread"],
        )

    assert follow_targets == []
    assert unread_targets == []
    assert any("follow target XML parse failed" in record.message for record in caplog.records)
    assert any("unread dm XML parse failed" in record.message for record in caplog.records)
