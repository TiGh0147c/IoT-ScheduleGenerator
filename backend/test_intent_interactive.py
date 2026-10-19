"""L5 复杂意图选择模式：备选展开与打包归一化测试。"""

from services import (
    _collect_l5_step_plan,
    _commands_same_device_same_goal,
    _expand_parallel_device_selection,
    _find_alternatives_for_step,
    _find_same_device_command_variants,
    _normalize_id,
    _resolve_command_uid,
    _select_all_devices_as_fallback,
    pack_intent_api_commands,
)


def _cmd(uid, device, e_id=24, weight=1, pref=None, device_weight=1, api_set=None):
    return {
        "uid": uid,
        "c_instance_id": device,
        "c_brand": device.split(":")[-1],
        "e_id": e_id,
        "e_name": "照明",
        "weight": weight,
        "preference_desc": pref,
        "device_weight": device_weight,
        "api_set": api_set if api_set is not None else [{"piid": 2, "siid": 3, "value": True}],
        "param_schema": None,
        "param_details": None,
    }


def _device(cid, brand, a_ref, weight=1):
    return {
        "c_instance_id": cid,
        "c_brand": brand,
        "a_ref": a_ref,
        "weight": weight,
        "preference_desc": None,
    }


def test_same_device_laundry_variants():
    device = "dev:washer-a"
    commands = [
        _cmd("洗衣机A：自动洗衣", device, e_id=20, weight=3, api_set=[{"siid": 2, "aiid": 1}]),
        _cmd(
            "洗衣机A：选择【自定义】模式洗衣并开始",
            device,
            e_id=20,
            weight=1,
            api_set=[{"siid": 2, "piid": 3, "value": "XX"}, {"siid": 2, "aiid": 1}],
        ),
        _cmd("洗衣机A：停止洗衣", device, e_id=20, api_set=[{"siid": 2, "aiid": 2}]),
        _cmd("洗衣机A：查询工作状态", device, e_id=20, api_set=[{"siid": 2, "piid": 1}]),
    ]
    by_uid = {_normalize_id(c["uid"]): c for c in commands}
    assert _commands_same_device_same_goal(commands[0], commands[1], "洗衬衣") is True
    assert _commands_same_device_same_goal(commands[0], commands[2], "洗衬衣") is False
    assert _commands_same_device_same_goal(commands[0], commands[3], "洗衬衣") is False

    variants = _find_same_device_command_variants(
        "洗衣机A：自动洗衣",
        commands,
        by_uid,
        step_intent="洗衬衣",
    )
    uids = [v["payload_uid"] for v in variants]
    assert "洗衣机A：自动洗衣" in uids
    assert "洗衣机A：选择【自定义】模式洗衣并开始" in uids
    assert "洗衣机A：停止洗衣" not in uids
    assert "洗衣机A：查询工作状态" not in uids
    for v in variants:
        assert v.get("goal_analysis")
        assert "指令" in v["goal_analysis"] or "路径" in v["goal_analysis"]
        assert "command_weight" in v
    assert variants[0]["command_weight"] == 3
    assert any(v["command_weight"] == 1 for v in variants[1:])
    # 指令权重最高者应排在第一位并作为推荐
    assert variants[0]["payload_uid"] == "洗衣机A：自动洗衣"
    assert variants[0]["is_recommended"] is True


def test_same_device_reject_open_light_vs_adjust():
    device = "dev:light-a"
    commands = [
        _cmd("灯A：打开灯", device, e_id=5, api_set=[{"value": True}]),
        _cmd("灯A：调节亮度", device, e_id=5, api_set=[{"piid": 3, "value": "XX"}]),
        _cmd("灯A：调节色温", device, e_id=5, api_set=[{"piid": 4, "value": "XX"}]),
        _cmd("灯A：关闭灯", device, e_id=5, api_set=[{"value": False}]),
    ]
    by_uid = {_normalize_id(c["uid"]): c for c in commands}
    assert _commands_same_device_same_goal(commands[0], commands[1], "打开灯") is False
    assert _commands_same_device_same_goal(commands[0], commands[2], "打开灯") is False
    assert _commands_same_device_same_goal(commands[0], commands[3], "打开灯") is False
    variants = _find_same_device_command_variants(
        "灯A：打开灯",
        commands,
        by_uid,
        step_intent="打开灯",
    )
    assert variants == []


def test_same_device_reject_start_clean_vs_stop():
    device = "dev:vacuum-a"
    commands = [
        _cmd("扫地机A：开始扫地", device, e_id=30, api_set=[{"aiid": 1}]),
        _cmd("扫地机A：关闭扫地", device, e_id=30, api_set=[{"aiid": 2}]),
        _cmd("扫地机A：停止清扫", device, e_id=30, api_set=[{"aiid": 3}]),
        _cmd("扫地机A：开启自动清扫", device, e_id=30, api_set=[{"aiid": 4}]),
    ]
    by_uid = {_normalize_id(c["uid"]): c for c in commands}
    assert _commands_same_device_same_goal(commands[0], commands[1], "开始扫地") is False
    assert _commands_same_device_same_goal(commands[0], commands[2], "开始扫地") is False
    assert _commands_same_device_same_goal(commands[0], commands[3], "开始扫地") is True
    variants = _find_same_device_command_variants(
        "扫地机A：开始扫地",
        commands,
        by_uid,
        step_intent="开始扫地",
    )
    uids = [v["payload_uid"] for v in variants]
    assert "扫地机A：开始扫地" in uids
    assert "扫地机A：开启自动清扫" in uids
    assert "扫地机A：关闭扫地" not in uids
    assert "扫地机A：停止清扫" not in uids


def test_same_device_no_variants_for_open_close():
    device = "dev:light-a"
    commands = [
        _cmd("灯A：打开灯", device, e_id=5, api_set=[{"value": True}]),
        _cmd("灯A：关闭灯", device, e_id=5, api_set=[{"value": False}]),
    ]
    by_uid = {_normalize_id(c["uid"]): c for c in commands}
    variants = _find_same_device_command_variants(
        "灯A：打开灯",
        commands,
        by_uid,
        step_intent="打开灯",
    )
    assert variants == []


def test_device_options_attach_command_variants():
    commands = [
        _cmd("洗衣机A：自动洗衣", "dev:washer-a", e_id=20, weight=2),
        _cmd("洗衣机A：选择【自定义】模式洗衣并开始", "dev:washer-a", e_id=20, weight=1),
        _cmd("洗衣机B：自动洗衣", "dev:washer-b", e_id=20, weight=4),
    ]
    by_uid = {_normalize_id(c["uid"]): c for c in commands}
    options = _find_alternatives_for_step(
        "洗衣机A：自动洗衣",
        commands,
        by_uid,
        step_intent="洗衬衣",
        max_options=5,
    )
    assert len(options) >= 2
    primary = next(o for o in options if o["payload_uid"] == "洗衣机A：自动洗衣")
    assert len(primary.get("command_variants") or []) >= 2
    assert primary.get("goal_analysis")
    assert primary.get("command_weight") == 2
    assert all(o.get("goal_analysis") for o in options)


def test_resolve_hallucinated_instance_action_uid():
    commands = [
        _cmd("ZOEE智能灯带：打开灯", "urn:miot-spec-v2:device:light:0000A001:zy1-wy0a01:1:0000C802"),
        _cmd("ZOEE智能灯带：关闭灯", "urn:miot-spec-v2:device:light:0000A001:zy1-wy0a01:1:0000C802", api_set=[{"value": False}]),
    ]
    by_uid = {_normalize_id(c["uid"]): c for c in commands}
    hallucinated = "urn:miot-spec-v2:device:light:0000A001:zy1-wy0a01:1:0000C802:打开灯"
    resolved = _resolve_command_uid(hallucinated, commands, by_uid)
    assert resolved == "ZOEE智能灯带：打开灯"


def test_collect_l5_step_plan_recovers_multi_steps():
    commands = [
        _cmd("ZOEE智能灯带：打开灯", "urn:light:a"),
        _cmd("VINO空调：制冷并将目标温度设置为XX℃", "urn:ac:a"),
        _cmd("REDMI显示器：打开电视", "urn:tv:a"),
        _cmd("REDMI显示器：关闭电视", "urn:tv:a", api_set=[{"value": False}]),
    ]
    by_uid = {_normalize_id(c["uid"]): c for c in commands}
    raw = {
        "ordered_uids": [
            "urn:light:a:打开灯",
            "urn:ac:a:制冷并将目标温度设置为XX℃",
            "urn:tv:a:打开电视",
        ],
        "steps": [
            {"step": 1, "intent": "打开灯", "recommended_uid": "urn:light:a:打开灯", "alternative_uids": []},
            {
                "step": 2,
                "intent": "客厅降温",
                "recommended_uid": "urn:ac:a:制冷并将目标温度设置为XX℃",
                "alternative_uids": [],
            },
            {"step": 3, "intent": "打开电视", "recommended_uid": "urn:tv:a:打开电视", "alternative_uids": []},
        ],
    }
    plan = _collect_l5_step_plan(raw, commands, by_uid)
    assert len(plan) == 3
    assert plan[0]["uid"] == "ZOEE智能灯带：打开灯"
    assert plan[1]["uid"] == "VINO空调：制冷并将目标温度设置为XX℃"
    assert plan[2]["uid"] == "REDMI显示器：打开电视"


def test_l4_expand_parallel_same_a_ref():
    devices = [
        _device("dev:light-a", "灯A", "灯", weight=1),
        _device("dev:light-b", "灯B", "灯", weight=1),
        _device("dev:ac-1", "空调1", "空调", weight=1),
    ]
    filtered = {
        "selected_nodes": [{"id": "dev:light-a", "name": "灯A", "reason": "相关"}],
        "relations": [],
        "nl_guidance": "",
    }
    out = _expand_parallel_device_selection(filtered, devices)
    ids = {str(n["id"]) for n in out["selected_nodes"]}
    assert "dev:light-a" in ids
    assert "dev:light-b" in ids
    assert "dev:ac-1" not in ids
    assert out.get("parallel_devices_expanded") == 1


def test_l4_interactive_fallback_selects_all():
    devices = [
        _device("dev:light-a", "灯A", "灯"),
        _device("dev:light-b", "灯B", "灯"),
    ]
    filtered = {"selected_nodes": [], "relations": [], "nl_guidance": ""}
    out = _select_all_devices_as_fallback(filtered, devices)
    assert len(out["selected_nodes"]) == 2
    assert out.get("fallback_applied") is True


def test_find_alternatives_cross_device_same_function():
    commands = [
        _cmd("灯A：打开灯", "dev:light-a", device_weight=2),
        _cmd("灯B：打开灯", "dev:light-b", device_weight=1),
        _cmd("灯C：打开灯", "dev:light-c", device_weight=3),
    ]
    by_uid = {_normalize_id(c["uid"]): c for c in commands}
    options = _find_alternatives_for_step("灯A：打开灯", commands, by_uid, max_options=5)
    uids = [o["payload_uid"] for o in options]
    assert "灯A：打开灯" in uids
    assert "灯B：打开灯" in uids
    assert "灯C：打开灯" in uids
    assert len(options) == 3
    # 设备权重降序：C(3) > A(2) > B(1)，最高权重为推荐
    assert uids == ["灯C：打开灯", "灯A：打开灯", "灯B：打开灯"]
    assert options[0]["is_recommended"] is True
    assert options[0]["payload_uid"] == "灯C：打开灯"
    weights = {o["payload_uid"]: o["device_weight"] for o in options}
    assert weights["灯A：打开灯"] == 2
    assert weights["灯C：打开灯"] == 3


def test_same_device_variants_rank_by_command_weight():
    device = "dev:washer-a"
    commands = [
        _cmd("洗衣机A：自动洗衣", device, e_id=20, weight=1, api_set=[{"siid": 2, "aiid": 1}]),
        _cmd(
            "洗衣机A：选择【自定义】模式洗衣并开始",
            device,
            e_id=20,
            weight=5,
            api_set=[{"siid": 2, "piid": 3, "value": "XX"}, {"siid": 2, "aiid": 1}],
        ),
    ]
    by_uid = {_normalize_id(c["uid"]): c for c in commands}
    variants = _find_same_device_command_variants(
        "洗衣机A：自动洗衣",
        commands,
        by_uid,
        step_intent="洗衬衣",
    )
    assert len(variants) >= 2
    assert variants[0]["payload_uid"] == "洗衣机A：选择【自定义】模式洗衣并开始"
    assert variants[0]["is_recommended"] is True
    assert variants[0]["command_weight"] == 5
    options = _find_alternatives_for_step(
        "洗衣机A：自动洗衣",
        commands,
        by_uid,
        step_intent="洗衬衣",
        max_options=5,
    )
    assert options[0]["payload_uid"] == "洗衣机A：选择【自定义】模式洗衣并开始"
    assert options[0]["command_weight"] == 5


def test_exclude_same_device_different_commands():
    commands = [
        _cmd("灯A：打开灯", "dev:light-a"),
        _cmd("灯A：关闭灯", "dev:light-a", api_set=[{"piid": 2, "siid": 3, "value": False}]),
        _cmd("灯A：调节亮度", "dev:light-a", api_set=[{"piid": 3, "siid": 3, "value": "XX"}]),
    ]
    by_uid = {_normalize_id(c["uid"]): c for c in commands}
    options = _find_alternatives_for_step("灯A：打开灯", commands, by_uid, max_options=5)
    assert len(options) == 1
    assert options[0]["payload_uid"] == "灯A：打开灯"


def test_exclude_opposite_action_on_other_device():
    commands = [
        _cmd("灯A：打开灯", "dev:light-a", api_set=[{"piid": 1, "siid": 2, "value": True}]),
        _cmd("灯B：关闭灯", "dev:light-b", api_set=[{"piid": 1, "siid": 2, "value": False}]),
    ]
    by_uid = {_normalize_id(c["uid"]): c for c in commands}
    options = _find_alternatives_for_step("灯A：打开灯", commands, by_uid, max_options=5)
    assert len(options) == 1
    assert options[0]["payload_uid"] == "灯A：打开灯"


def test_pack_uses_selected_uid_from_options():
    final_plan = {
        "plan_summary": "测试",
        "ordered_steps": [
            {
                "step": 1,
                "payload_uid": "旧uid",
                "selected_uid": "新uid",
                "c_instance_id": "dev:1",
                "c_brand": "设备1",
                "e_id": 1,
                "e_name": "效果",
                "nl_step": "执行",
                "options": [
                    {
                        "payload_uid": "新uid",
                        "c_instance_id": "dev:1",
                        "c_brand": "设备1",
                        "e_id": 1,
                        "e_name": "效果",
                        "nl_step": "执行新",
                        "device_weight": 2,
                        "api_set": [{"piid": 1, "siid": 2, "value": 26}],
                        "param_placeholders": [],
                    }
                ],
                "param_placeholders": [],
                "api_set": [{"piid": 9, "siid": 9, "value": "XX"}],
            }
        ],
    }
    result = pack_intent_api_commands(
        intent_text="测试",
        final_plan=final_plan,
        user_param_values={},
    )
    assert result["success"] is True
    assert result["packed_steps"][0]["payload_uid"] == "新uid"
    assert result["packed_steps"][0]["api_set"] == [{"piid": 1, "siid": 2, "value": 26}]


if __name__ == "__main__":
    test_same_device_laundry_variants()
    test_same_device_reject_open_light_vs_adjust()
    test_same_device_reject_start_clean_vs_stop()
    test_same_device_no_variants_for_open_close()
    test_device_options_attach_command_variants()
    test_resolve_hallucinated_instance_action_uid()
    test_collect_l5_step_plan_recovers_multi_steps()
    test_l4_expand_parallel_same_a_ref()
    test_l4_interactive_fallback_selects_all()
    test_find_alternatives_cross_device_same_function()
    test_same_device_variants_rank_by_command_weight()
    test_exclude_same_device_different_commands()
    test_exclude_opposite_action_on_other_device()
    test_pack_uses_selected_uid_from_options()
    print("All intent interactive tests passed")
