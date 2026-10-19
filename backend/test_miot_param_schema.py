"""miot_param_schema 单元测试（洗衣机模式枚举、空调温度范围）。"""
import json
import os

from miot_param_schema import (
    build_miot_param_index,
    build_nl_param_description,
    build_param_schema,
    enrich_commands_with_param_schema,
    merge_effective_param_slots,
)


def test_washer_mode_enum():
    spec_path = os.path.join(
        os.path.dirname(__file__),
        "米家洗衣机 超净洗Pro 洗烘12kg - 产品规格 - Xiaomi Miot Spec.json",
    )
    if not os.path.exists(spec_path):
        print("SKIP: spec file not found")
        return

    with open(spec_path, "r", encoding="utf-8") as f:
        api_doc = json.load(f)

    index = build_miot_param_index(api_doc)
    assert (2, 3) in index
    mode_meta = index[(2, 3)]
    assert mode_meta["property_desc"] == "模式"
    assert mode_meta["value_type"] == "enum"
    assert len(mode_meta["options"]) >= 10
    labels = [o["label_zh"] for o in mode_meta["options"]]
    assert "快速洗" in labels
    assert "混合洗" in labels

    api_set = [{"siid": 2, "piid": 3, "value": "XX"}, {"siid": 2, "piid": 1, "value": True}]
    schema = build_param_schema(api_set, api_doc)
    assert schema is not None
    assert len(schema["slots"]) == 1
    slot = schema["slots"][0]
    assert slot["path"] == "api_set[0].value"
    assert slot["property_desc"] == "模式"
    assert any(o["label_zh"] == "快速洗" for o in slot["options"])

    commands = [{"uid": "test", "api_set": api_set}]
    enrich_commands_with_param_schema(commands, api_doc)
    assert "param_schema" in commands[0]
    print("OK: washer mode enum test passed")


def test_ac_target_temperature_nl_description():
    spec_path = os.path.join(
        os.path.dirname(__file__),
        "Test_Data",
        "Standard_API_Doc",
        "小米互联网空调A（1.5匹_变频_一级能效） - 产品规格 - Xiaomi Miot Spec.json",
    )
    if not os.path.exists(spec_path):
        print("SKIP: AC spec file not found")
        return

    with open(spec_path, "r", encoding="utf-8") as f:
        api_doc = json.load(f)

    index = build_miot_param_index(api_doc)
    assert (2, 4) in index
    temp_meta = index[(2, 4)]
    assert temp_meta["property_desc"] == "设定温度"
    assert temp_meta["value_type"] == "range"
    assert temp_meta["value_range"]["min"] == 16
    assert temp_meta["value_range"]["max"] == 31
    assert temp_meta["value_range"]["step"] == 0.5

    api_set = [{"siid": 2, "piid": 4, "value": "XX"}]
    schema = build_param_schema(api_set, api_doc)
    assert schema is not None
    slot = schema["slots"][0]
    assert slot["nl_description"]
    assert "设定温度" in slot["nl_description"]
    assert "浮点数" in slot["nl_description"]
    assert "16" in slot["nl_description"] and "31" in slot["nl_description"]
    assert "摄氏度" in slot["nl_description"]

    merged = merge_effective_param_slots(schema)[0]
    assert merged["hint"] == slot["nl_description"]
    assert "用于调节空调的设定温度" in merged["hint"]

    desc = build_nl_param_description({"property_desc": "设定温度", "format": "float", "unit": "celsius", "value_range": {"min": 16, "max": 31, "step": 0.5}})
    assert "设定温度" in desc
    print("OK: AC target temperature NL description test passed")


def test_google_home_param_schema():
    from miot_param_schema import build_google_param_index, build_param_schema, inject_params_into_api_set

    api_doc = {
        "doc_source": "google-home-cloud-to-cloud",
        "google_type": "action.devices.types.AC_UNIT",
        "traits": [{"name": "OnOff", "fqn": "action.devices.traits.OnOff"}],
        "functions": [
            {
                "function_id": "setpoint",
                "apis": [
                    {
                        "command": "action.devices.commands.ThermostatTemperatureSetpoint",
                        "params_schema": {
                            "thermostatTemperatureSetpoint": {
                                "type": "number",
                                "required": True,
                                "description": "目标温度（℃）",
                            }
                        },
                    }
                ],
            }
        ],
    }
    index = build_google_param_index(api_doc)
    assert "action.devices.commands.ThermostatTemperatureSetpoint" in index
    api_set = [
        {
            "command": "action.devices.commands.ThermostatTemperatureSetpoint",
            "params": {"thermostatTemperatureSetpoint": "XX"},
        }
    ]
    schema = build_param_schema(api_set, api_doc)
    assert schema is not None
    assert schema["source"]["doc_type"] == "google-home-cloud-to-cloud"
    assert schema["slots"][0]["path"] == "api_set[0].params.thermostatTemperatureSetpoint"
    assert "目标温度" in schema["slots"][0]["property_desc"]

    injected, applied = inject_params_into_api_set(
        api_set,
        [{"path": "api_set[0].params.thermostatTemperatureSetpoint", "value": "26", "value_type": "range", "format": "float"}],
    )
    assert injected[0]["params"]["thermostatTemperatureSetpoint"] == 26.0
    assert len(applied) == 1
    print("OK: Google Home param_schema test passed")


if __name__ == "__main__":
    test_washer_mode_enum()
    test_ac_target_temperature_nl_description()
    test_google_home_param_schema()
