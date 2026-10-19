"""意图 API 指令集打包与参数注入单元测试。"""
import json

from miot_param_schema import coerce_param_value, inject_params_into_api_set
from services import pack_intent_api_commands, write_api_command_log


def test_inject_api_set_value():
    api_set = [
        {"siid": 2, "piid": 1, "value": True},
        {"siid": 2, "piid": 4, "value": "XX"},
    ]
    injected, applied = inject_params_into_api_set(
        api_set,
        [
            {
                "path": "api_set[1].value",
                "value": "26",
                "value_type": "range",
                "format": "float",
                "label": "设定温度",
                "unit": "celsius",
            }
        ],
    )
    assert injected[1]["value"] == 26.0
    assert len(applied) == 1
    assert applied[0]["value"] == 26.0
    print("OK: inject api_set value")


def test_coerce_bool_and_int():
    assert coerce_param_value("开", value_type="bool") is True
    assert coerce_param_value("0", value_type="bool") is False
    assert coerce_param_value("80", value_type="range", fmt="uint8") == 80
    print("OK: coerce param values")


def test_pack_intent_api_commands():
    final_plan = {
        "plan_summary": "先开灯再降温",
        "nl_guidance": "并行执行",
        "ordered_steps": [
            {
                "step": 1,
                "payload_uid": "灯：设置亮度",
                "c_instance_id": "light-1",
                "c_brand": "测试灯",
                "e_name": "照明",
                "nl_step": "设置亮度为XX%",
                "api_set": [{"siid": 2, "piid": 2, "value": "XX"}],
                "param_placeholders": [
                    {
                        "path": "api_set[0].value",
                        "label": "亮度",
                        "value_type": "range",
                        "format": "uint8",
                        "unit": "percentage",
                    }
                ],
            },
            {
                "step": 2,
                "payload_uid": "空调：制冷",
                "c_instance_id": "ac-1",
                "c_brand": "测试空调",
                "e_name": "制冷",
                "nl_step": "制冷并将目标温度设置为XX℃",
                "api_set": [{"siid": 2, "piid": 4, "value": "XX"}],
                "param_placeholders": [
                    {
                        "path": "api_set[0].value",
                        "label": "设定温度",
                        "value_type": "range",
                        "format": "float",
                        "unit": "celsius",
                    }
                ],
            },
        ],
    }
    user_values = {
        "1-api_set[0].value": "60",
        "2-api_set[0].value": "26",
    }
    result = pack_intent_api_commands(
        trace_id="test-trace",
        intent_text="客厅开灯并降温",
        final_plan=final_plan,
        user_param_values=user_values,
    )
    assert result["success"] is True
    assert len(result["packed_steps"]) == 2
    assert result["packed_steps"][0]["api_set"][0]["value"] == 60
    assert result["packed_steps"][1]["api_set"][0]["value"] == 26.0
    assert "60" in result["packed_steps"][0]["step_description"]
    print("OK: pack intent api commands")


def test_pack_validation_missing_param():
    final_plan = {
        "plan_summary": "测试",
        "ordered_steps": [
            {
                "step": 1,
                "payload_uid": "灯：设置亮度",
                "api_set": [{"value": "XX"}],
                "param_placeholders": [{"path": "api_set[0].value", "label": "亮度"}],
            }
        ],
    }
    result = pack_intent_api_commands(
        intent_text="测试",
        final_plan=final_plan,
        user_param_values={},
    )
    assert result["success"] is False
    assert result["validation_errors"]
    print("OK: pack validation")


def test_pack_skips_optional_unfilled_params():
    final_plan = {
        "plan_summary": "洗衣",
        "ordered_steps": [
            {
                "step": 1,
                "payload_uid": "洗衣机：选择洗涤程序为XX并开始",
                "api_set": [
                    {"siid": 2, "piid": 1, "value": "XX"},
                    {"siid": 2, "piid": 4, "value": "XX"},
                ],
                "param_placeholders": [
                    {"path": "api_set[0].value", "label": "程序", "required": True},
                    {"path": "api_set[1].value", "label": "水温", "required": False},
                ],
            }
        ],
    }
    result = pack_intent_api_commands(
        intent_text="羊毛洗",
        final_plan=final_plan,
        user_param_values={"1-api_set[0].value": "wool"},
    )
    assert result["success"] is True
    assert result["packed_steps"][0]["api_set"][0]["value"] == "wool"
    assert len(result["packed_steps"][0]["api_set"]) == 1
    print("OK: pack skips optional params")


def test_pack_uses_placeholder_user_value():
    final_plan = {
        "plan_summary": "洗衣",
        "ordered_steps": [
            {
                "step": 1,
                "payload_uid": "洗衣机：选择洗涤程序为XX并开始",
                "api_set": [{"siid": 2, "piid": 1, "value": "XX"}],
                "param_placeholders": [
                    {
                        "path": "api_set[0].value",
                        "label": "程序",
                        "required": True,
                        "user_value": "wool",
                    }
                ],
            }
        ],
    }
    result = pack_intent_api_commands(
        intent_text="羊毛洗",
        final_plan=final_plan,
        user_param_values={},
    )
    assert result["success"] is True
    assert result["packed_steps"][0]["api_set"][0]["value"] == "wool"
    print("OK: pack uses bound user_value")


def test_write_api_command_log(tmp_path, monkeypatch):
    import services as svc

    monkeypatch.setattr(svc, "API_COMMAND_LOG_DIR", str(tmp_path))
    log_path = write_api_command_log(
        trace_id="t1",
        intent_text="开灯",
        final_plan={"plan_summary": "开灯", "ordered_steps": [], "resolve_mode": "interactive"},
        user_param_values={},
        packed_api_set=[{"step": 1, "api_set": [{"siid": 2}]}],
        packed_steps=[{"step": 1, "step_description": "开灯"}],
    )
    assert log_path
    with open(log_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "开灯" in content
    assert "【最终 API 指令集】" in content
    assert "【0. 调用模式】" in content
    assert "复杂模式" in content
    assert "APIcommand-" in log_path
    print("OK: write api command log")


def test_write_intent_trace_log_mode_filename(tmp_path, monkeypatch):
    import services as svc
    from datetime import datetime

    monkeypatch.setattr(svc, "INTENT_TRACE_DIR", str(tmp_path))
    auto_path = svc.write_intent_trace_log(
        trace_id="t-auto",
        intent_text="开灯",
        started_at=datetime(2026, 7, 22, 12, 0, 0),
        layers_trace=[],
        final_plan={"resolve_mode": "auto", "ordered_steps": []},
        packed_api_set=[],
        stopped_at=None,
        message="ok",
    )
    complex_path = svc.write_intent_trace_log(
        trace_id="t-complex",
        intent_text="开灯",
        started_at=datetime(2026, 7, 22, 12, 0, 1),
        layers_trace=[],
        final_plan={"resolve_mode": "interactive", "ordered_steps": []},
        packed_api_set=[],
        stopped_at=None,
        message="ok",
    )
    assert "trace-auto-" in auto_path
    assert "trace-complex-" in complex_path
    with open(auto_path, "r", encoding="utf-8") as f:
        assert "自动模式" in f.read()
    with open(complex_path, "r", encoding="utf-8") as f:
        assert "复杂模式" in f.read()
    print("OK: trace mode filenames")


if __name__ == "__main__":
    test_inject_api_set_value()
    test_coerce_bool_and_int()
    test_pack_intent_api_commands()
    test_pack_validation_missing_param()
    test_pack_skips_optional_unfilled_params()
    test_pack_uses_placeholder_user_value()
    print("All intent pack tests passed")
