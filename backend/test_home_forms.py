"""家居库：L5 UID 命名空间与房间口语加权。"""
from home_forms import (
    annotate_device_room_match,
    build_command_weight_editor,
    placement_display_name,
    stamp_l5_placement,
)


def test_stamp_l5_namespaces_uid():
    cands = [{"uid": "空调：制冷", "c_instance_id": "ac-1", "c_brand": "VINO空调"}]
    out = stamp_l5_placement(
        cands,
        {
            "placement_id": "plc-1",
            "catalog_c_instance_id": "ac-1",
            "display_name": "主卧空调",
            "alias": "主卧空调",
            "room_label": "主卧",
        },
    )
    assert out[0]["uid"] == "plc-1::空调：制冷"
    assert out[0]["source_uid"] == "空调：制冷"
    assert out[0]["primary_payload_uid"] == "空调：制冷"
    assert out[0]["c_instance_id"] == "plc-1"
    assert out[0]["placement_id"] == "plc-1"
    assert out[0]["catalog_c_instance_id"] == "ac-1"
    assert out[0]["c_brand"] == "主卧空调"
    assert out[0]["room_label"] == "主卧"
    print("OK: stamp_l5_namespaces_uid")


def test_room_match_scores_label():
    devices = [
        {"room_label": "客厅", "room_type_name": "客厅", "alias": "大厅空调"},
        {"room_label": "主卧", "room_type_name": "卧室", "alias": "卧室空调"},
        {"room_label": "", "room_type_name": "", "alias": "备用空调"},
    ]
    annotate_device_room_match("客厅太热", devices)
    assert devices[0]["room_match_score"] >= 3
    assert "客厅" in devices[0]["room_match_hint"]
    assert devices[1]["room_match_score"] == 0
    assert devices[2]["room_match_score"] == 0
    print("OK: room_match_scores_label")


def test_display_name_with_room():
    named = placement_display_name(
        alias="空调",
        catalog_brand="VINO",
        catalog_id="ac-1",
        room_label="客厅",
    )
    assert named == "空调（客厅）"
    fallback = placement_display_name(alias="", catalog_brand="VINO", catalog_id="ac-1", room_label="")
    assert fallback == "VINO"
    print("OK: display_name_with_room")


def _atom(uid, kind, **extra):
    row = {
        "uid": uid,
        "c_instance_id": "ac-1",
        "e_id": extra.pop("e_id", None),
        "api_set": extra.pop("api_set", [{"siid": 2, "piid": 1, "value": "on"}]),
        "capability_kind": kind,
        "capability_desc": extra.pop("capability_desc", uid),
        "supports_e_ids": extra.pop("supports_e_ids", []),
        "env_impact": extra.pop("env_impact", []),
        "interpretation": extra.pop("interpretation", {"l5_visible": True}),
        "param_schema": extra.pop("param_schema", None),
    }
    row.update(extra)
    return row


def test_command_weight_editor_groups_recipes():
    payloads = [
        _atom("空调：开机", "auxiliary", capability_desc="打开设备"),
        _atom("空调：制冷", "effect", e_id=1, capability_desc="制冷运行", env_impact=[10]),
        _atom(
            "空调：设定温度",
            "parameter",
            supports_e_ids=[1],
            capability_desc="设定目标温度",
            param_schema={"slots": [{"path": "api_set[0].value", "property_desc": "设定温度"}]},
        ),
        _atom("空调：制热", "effect", e_id=2, capability_desc="制热运行"),
        _atom(
            "空调：睡眠",
            "strategy",
            capability_desc="睡眠模式",
            interpretation={"l5_visible": True, "possible_intents": ["睡眠"]},
        ),
        _atom(
            "空调：黄金洗",
            "effect",
            e_id=1,
            interpretation={"l5_visible": False, "exposure": "lazy"},
        ),
    ]
    recipes = [
        {
            "recipe_uid": "rec-cool",
            "c_instance_id": "ac-1",
            "recipe_name": "制冷到目标温度",
            "covers_effects": [1],
            "steps": [
                {"uid": "空调：开机", "role": "auxiliary"},
                {"uid": "空调：制冷", "role": "effect"},
                {"uid": "空调：设定温度", "role": "parameter"},
            ],
            "extra": {"recipe_desc": "开机后制冷并设温", "daily_use": "觉得热时"},
        },
        {
            "recipe_uid": "rec-cool-short",
            "c_instance_id": "ac-1",
            "recipe_name": "制冷",
            "covers_effects": [1],
            "steps": [
                {"uid": "空调：开机", "role": "auxiliary"},
                {"uid": "空调：制冷", "role": "effect"},
            ],
            "extra": {},
        },
        {
            "recipe_uid": "rec-lazy",
            "c_instance_id": "ac-1",
            "recipe_name": "黄金洗",
            "steps": [{"uid": "空调：黄金洗", "role": "effect"}],
            "extra": {"exposure": "lazy"},
        },
    ]
    editor = build_command_weight_editor(
        placement_id="plc-1",
        payloads=payloads,
        recipes=recipes,
        pref_by_uid={"空调：制冷": {"weight": 3}, "空调：制热": {"weight": 1}, "空调：睡眠": {"weight": 0}},
        effect_name_map={1: "制冷", 2: "制热"},
        env_name_map={10: "室内气温"},
    )
    names = [r["recipe_name"] for r in editor["recipes"]]
    assert "制冷到目标温度" in names
    assert "制冷" in names
    assert "黄金洗" not in names
    cool = next(r for r in editor["recipes"] if r["recipe_name"] == "制冷到目标温度")
    assert cool["effective_weight"] == 3
    assert cool["weight_payload_uids"] == ["空调：制冷"]
    assert cool["cover_effect_names"] == ["制冷"]
    assert [s["uid"] for s in cool["steps"]] == ["空调：开机", "空调：制冷", "空调：设定温度"]
    assert cool["steps"][0]["weight_editable"] is False
    assert cool["steps"][1]["weight_editable"] is True
    assert cool["steps"][2]["param_labels"] == ["设定温度"]
    short = next(r for r in editor["recipes"] if r["recipe_name"] == "制冷")
    assert short["shadowed"] is True
    assert "制冷到目标温度" in short["shadowed_by"]
    assert editor["uncovered_payload_uids"] == ["空调：制热", "空调：睡眠"]
    cool_cmd = next(c for c in editor["commands"] if c["payload_uid"] == "空调：制冷")
    assert cool_cmd["e_name"] == "制冷"
    assert "制冷到目标温度" in cool_cmd["covered_by_recipes"]
    assert next(c for c in editor["commands"] if c["payload_uid"] == "空调：睡眠")["weight"] == 0
    assert all(c["payload_uid"] != "空调：设定温度" for c in editor["commands"])
    assert all(c["payload_uid"] != "空调：黄金洗" for c in editor["commands"])
    print("OK: command_weight_editor_groups_recipes")


if __name__ == "__main__":
    test_stamp_l5_namespaces_uid()
    test_room_match_scores_label()
    test_display_name_with_room()
    test_command_weight_editor_groups_recipes()
    print("home_forms tests passed")
