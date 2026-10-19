"""L5 配方展开 / 参数挂槽 / 口语绑定 单测。"""

from intent_compose import (
    annotate_device_env_match,
    bind_placeholders_from_intent,
    bind_plan_placeholders,
    combo_intent_score,
    compose_l5_candidates,
    drop_subset_recipes,
    hinted_env_match_keys,
    is_pref_eligible_payload,
    merge_step_payloads,
    remap_api_set_path,
    reachable_device_ids,
    wanted_env_from_effect_ids,
)
from effect_env_combos import resolve_effect_combo


def _effect(uid, e_id=19, kind="effect", **extra):
    row = {
        "uid": uid,
        "c_instance_id": extra.pop("c_instance_id", "washer-1"),
        "e_id": e_id,
        "api_set": extra.pop("api_set", [{"siid": 2, "piid": 1, "value": "XX"}]),
        "param_schema": extra.pop(
            "param_schema",
            {
                "slots": [
                    {
                        "path": "api_set[0].value",
                        "value_type": "enum",
                        "property_desc": "洗涤程序",
                        "options": [
                            {"value": "wool", "label_zh": "羊毛洗"},
                            {"value": "mix", "label_zh": "混合洗"},
                        ],
                    }
                ]
            },
        ),
        "capability_kind": kind,
        "supports_e_ids": extra.pop("supports_e_ids", []),
        "interpretation": extra.pop("interpretation", {"l5_visible": True, "exposure": "generic"}),
    }
    row.update(extra)
    return row


def _param(uid, supports, label="水温"):
    return {
        "uid": uid,
        "c_instance_id": "washer-1",
        "e_id": None,
        "api_set": [{"siid": 2, "piid": 4, "value": "XX"}],
        "param_schema": {
            "slots": [
                {
                    "path": "api_set[0].value",
                    "value_type": "range",
                    "property_desc": label,
                    "unit": "celsius",
                    "label": label,
                }
            ]
        },
        "capability_kind": "parameter",
        "supports_e_ids": supports,
        "interpretation": {"l5_visible": True},
    }


def test_remap_api_set_path():
    assert remap_api_set_path("api_set[0].value", 2) == "api_set[2].value"
    assert remap_api_set_path("api_set[1].params.temp", 3) == "api_set[4].params.temp"
    print("OK: remap path")


def test_merge_recipe_optional_slots():
    payloads = {
        "洗：程序XX": _effect("洗：程序XX"),
        "洗：水温XX": _param("洗：水温XX", [19]),
    }
    merged = merge_step_payloads(
        [{"uid": "洗：程序XX", "role": "effect"}, {"uid": "洗：水温XX", "role": "parameter"}],
        payloads,
    )
    assert merged is not None
    assert len(merged["api_set"]) == 2
    slots = merged["param_schema"]["slots"]
    assert slots[0]["path"] == "api_set[0].value"
    assert slots[0]["required"] is True
    assert slots[1]["path"] == "api_set[1].value"
    assert slots[1]["required"] is False
    print("OK: merge optional slots")


def test_drop_subset_recipes():
    short = {
        "recipe_uid": "a：制冷",
        "c_instance_id": "ac-1",
        "steps": [{"uid": "开"}, {"uid": "制冷"}],
    }
    full = {
        "recipe_uid": "a：制冷到目标温度",
        "c_instance_id": "ac-1",
        "steps": [{"uid": "开"}, {"uid": "制冷"}, {"uid": "温度"}],
    }
    kept = drop_subset_recipes([short, full])
    assert [r["recipe_uid"] for r in kept] == ["a：制冷到目标温度"]
    print("OK: drop subset recipes")


def test_compose_recipe_hides_lazy_and_attaches_params():
    generic = _effect("洗衣机：选择洗涤程序为XX并开始")
    lazy = _effect(
        "洗衣机：设置模式为羊毛洗",
        interpretation={"l5_visible": False, "exposure": "lazy", "specializes_uid": generic["uid"]},
        param_schema=None,
        api_set=[{"siid": 2, "piid": 1, "value": "wool"}],
    )
    temp = _param("洗衣机：设置洗涤水温为XX", [19], "洗涤水温")
    recipes = [
        {
            "recipe_uid": "洗衣机：选择洗涤程序为XX并开始",
            "c_instance_id": "washer-1",
            "recipe_name": "选择洗涤程序为XX并开始",
            "covers_effects": [19],
            "steps": [
                {"uid": generic["uid"], "role": "effect"},
                {"uid": temp["uid"], "role": "parameter"},
            ],
            "extra": {"exposure": "generic", "pattern": "program_enum"},
        },
        {
            "recipe_uid": "洗衣机：快捷羊毛洗",
            "c_instance_id": "washer-1",
            "recipe_name": "快捷羊毛洗",
            "covers_effects": [19],
            "steps": [{"uid": lazy["uid"], "role": "effect"}],
            "extra": {"exposure": "lazy", "bound_enum": "羊毛洗"},
        },
    ]
    cands = compose_l5_candidates(
        payloads=[generic, lazy, temp],
        recipes=recipes,
        pref_by_uid={generic["uid"]: {"weight": 1}},
        device_pref_by_id={"washer-1": {"weight": 2}},
        selected_e_ids={19},
        effect_name_map={19: "洗衣"},
        device_brand_map={"washer-1": "测试洗衣机"},
        intent_text="用羊毛洗 40度 洗衣服",
    )
    assert len(cands) == 1
    cand = cands[0]
    assert cand["candidate_kind"] == "recipe"
    assert cand["e_id"] == 19
    assert len(cand["api_set"]) == 2
    slots = cand["param_schema"]["slots"]
    assert slots[0]["user_value"] == "wool"
    assert str(slots[1]["user_value"]) == "40"
    assert "洗衣机：设置模式为羊毛洗" not in [c["uid"] for c in cands]
    print("OK: compose recipe + bind enum/temp")


def test_lazy_weight_inherits_to_generic_recipe():
    generic = _effect("洗衣机：选择洗涤程序为XX并开始")
    lazy = _effect(
        "洗衣机：设置模式为羊毛洗",
        interpretation={"l5_visible": False, "exposure": "lazy", "specializes_uid": generic["uid"]},
        param_schema=None,
    )
    recipes = [
        {
            "recipe_uid": "洗衣机：选择洗涤程序为XX并开始",
            "c_instance_id": "washer-1",
            "recipe_name": "选择洗涤程序为XX并开始",
            "covers_effects": [19],
            "steps": [{"uid": generic["uid"], "role": "effect"}],
            "extra": {"exposure": "generic", "pattern": "program_enum"},
        }
    ]
    cands = compose_l5_candidates(
        payloads=[generic, lazy],
        recipes=recipes,
        pref_by_uid={lazy["uid"]: {"weight": 3}},
        device_pref_by_id={"washer-1": {"weight": 1}},
        selected_e_ids={19},
        effect_name_map={19: "洗衣"},
        device_brand_map={"washer-1": "测试洗衣机"},
    )
    assert len(cands) == 1
    assert cands[0]["weight"] == 3
    print("OK: lazy weight inherits")


def test_filter_l3_drops_unrelated_recipe():
    cool = _effect("空调：制冷", e_id=1, c_instance_id="ac-1", param_schema=None, api_set=[{"siid": 2, "piid": 1, "value": True}])
    recipes = [
        {
            "recipe_uid": "空调：制冷",
            "c_instance_id": "ac-1",
            "recipe_name": "制冷",
            "covers_effects": [1],
            "steps": [{"uid": cool["uid"], "role": "effect"}],
            "extra": {"pattern": "gate+regime"},
        }
    ]
    cands = compose_l5_candidates(
        payloads=[cool],
        recipes=recipes,
        pref_by_uid={cool["uid"]: {"weight": 1}},
        device_pref_by_id={"ac-1": {"weight": 1}},
        selected_e_ids={19},
        filter_by_l3=True,
        effect_name_map={1: "制冷"},
        device_brand_map={"ac-1": "空调"},
    )
    assert cands == []
    print("OK: L3 filter")


def test_fallback_atom_attaches_supports_e_ids():
    light = {
        "uid": "灯：开灯",
        "c_instance_id": "light-1",
        "e_id": 24,
        "api_set": [{"siid": 2, "piid": 1, "value": True}],
        "param_schema": None,
        "capability_kind": "effect",
        "supports_e_ids": [],
        "interpretation": {"l5_visible": True},
    }
    bright = {
        "uid": "灯：设置亮度为XX",
        "c_instance_id": "light-1",
        "e_id": None,
        "api_set": [{"siid": 2, "piid": 2, "value": "XX"}],
        "param_schema": {
            "slots": [{"path": "api_set[0].value", "value_type": "range", "property_desc": "亮度"}]
        },
        "capability_kind": "parameter",
        "supports_e_ids": [24],
        "interpretation": {"l5_visible": True},
    }
    cands = compose_l5_candidates(
        payloads=[light, bright],
        recipes=[],
        pref_by_uid={light["uid"]: {"weight": 1}},
        device_pref_by_id={"light-1": {"weight": 1}},
        selected_e_ids={24},
        effect_name_map={24: "照明"},
        device_brand_map={"light-1": "灯"},
    )
    assert len(cands) == 1
    assert cands[0]["candidate_kind"] == "composed"
    assert len(cands[0]["api_set"]) == 2
    assert cands[0]["param_schema"]["slots"][0]["required"] is False
    print("OK: fallback attach params")


def test_reachable_includes_parameter_supports():
    payloads = [_param("洗：水温XX", [19])]
    ids = reachable_device_ids(payloads, [], {19})
    assert ids == {"washer-1"}
    print("OK: reachable via supports_e_ids")


def test_pref_eligible_skips_lazy_and_parameter():
    assert is_pref_eligible_payload(_effect("洗衣机：选择洗涤程序为XX并开始")) is True
    assert (
        is_pref_eligible_payload(
            _effect(
                "洗衣机：羊毛洗",
                interpretation={"l5_visible": False, "exposure": "lazy"},
            )
        )
        is False
    )
    assert is_pref_eligible_payload(_param("洗：水温", [19])) is False
    sleep = {
        "uid": "空调：设置模式为睡眠",
        "c_instance_id": "ac-1",
        "e_id": None,
        "api_set": [{"siid": 2, "piid": 2, "value": 5}],
        "capability_kind": "strategy",
        "supports_e_ids": [],
        "interpretation": {"l5_visible": True, "strategy_subtype": "scene", "possible_intents": ["睡眠模式"]},
    }
    assert is_pref_eligible_payload(sleep) is True
    print("OK: pref eligible")


def test_strategy_named_gate_for_l5():
    cool = {
        "uid": "空调：设置模式为制冷",
        "c_instance_id": "ac-1",
        "e_id": 1,
        "api_set": [{"siid": 2, "piid": 2, "value": 2}],
        "capability_kind": "effect",
        "supports_e_ids": [],
        "interpretation": {"l5_visible": True},
    }
    sleep = {
        "uid": "空调：设置模式为睡眠",
        "c_instance_id": "ac-1",
        "e_id": None,
        "api_set": [{"siid": 2, "piid": 2, "value": 5}],
        "capability_kind": "strategy",
        "supports_e_ids": [],
        "interpretation": {
            "l5_visible": True,
            "strategy_subtype": "scene",
            "possible_intents": ["打开睡眠模式", "睡眠模式"],
        },
    }
    auto = {
        "uid": "空调：设置模式为自动",
        "c_instance_id": "ac-1",
        "e_id": None,
        "api_set": [{"siid": 2, "piid": 2, "value": 0}],
        "capability_kind": "strategy",
        "supports_e_ids": [1, 11, 13],
        "interpretation": {
            "l5_visible": True,
            "strategy_subtype": "composite",
            "possible_intents": ["自动模式", "调成自动"],
        },
    }
    prefs = {cool["uid"]: {"weight": 1}, sleep["uid"]: {"weight": 1}, auto["uid"]: {"weight": 1}}
    cooling = compose_l5_candidates(
        payloads=[cool, sleep, auto],
        recipes=[],
        pref_by_uid=prefs,
        device_pref_by_id={"ac-1": {"weight": 1}},
        selected_e_ids={1},
        filter_by_l3=True,
        effect_name_map={1: "制冷"},
        device_brand_map={"ac-1": "空调"},
        intent_text="制冷",
    )
    cooling_uids = {c["primary_payload_uid"] for c in cooling}
    assert cool["uid"] in cooling_uids
    assert sleep["uid"] not in cooling_uids
    assert auto["uid"] not in cooling_uids

    named = compose_l5_candidates(
        payloads=[cool, sleep, auto],
        recipes=[],
        pref_by_uid=prefs,
        device_pref_by_id={"ac-1": {"weight": 1}},
        selected_e_ids={1},
        filter_by_l3=True,
        effect_name_map={1: "制冷"},
        device_brand_map={"ac-1": "空调"},
        intent_text="打开睡眠模式",
    )
    named_uids = {c["primary_payload_uid"] for c in named}
    assert sleep["uid"] in named_uids
    assert auto["uid"] not in named_uids

    mode_only = compose_l5_candidates(
        payloads=[cool, sleep, auto],
        recipes=[],
        pref_by_uid=prefs,
        device_pref_by_id={"ac-1": {"weight": 1}},
        selected_e_ids={1},
        filter_by_l3=True,
        effect_name_map={1: "制冷"},
        device_brand_map={"ac-1": "空调"},
        intent_text="模式",
    )
    mode_uids = {c["primary_payload_uid"] for c in mode_only}
    assert sleep["uid"] not in mode_uids
    assert auto["uid"] not in mode_uids

    reachable = reachable_device_ids([sleep], [], {1})
    assert reachable == set()
    print("OK: strategy named gate")


def test_bind_placeholders_from_intent():
    placeholders = [
        {
            "path": "api_set[0].value",
            "value_type": "enum",
            "options": [{"value": "wool", "label_zh": "羊毛洗"}],
        },
        {"path": "api_set[1].value", "value_type": "range", "label": "洗涤水温", "unit": "celsius"},
    ]
    bind_placeholders_from_intent("羊毛洗40度", placeholders)
    assert placeholders[0]["user_value"] == "wool"
    assert placeholders[1]["user_value"] == "40"
    print("OK: bind from intent")


def test_bind_plan_does_not_spray_temperature():
    text = (
        "今天太热了，我出了一身汗，先把灯打开，给客厅降降温，调到22度吧，"
        "然后把电视打开，我刚给冰箱里放了几罐饮料，让它们冷的快点，再给我的几件衬衣洗了"
    )
    steps = [
        {
            "step": 2,
            "c_brand": "米家新风空调 1.5匹 新一级（客厅）",
            "c_instance_id": "ac-1",
            "e_name": "制冷",
            "step_intent": "开启客厅空调制冷，设定目标温度为22度（温度占位XX）。",
            "param_placeholders": [
                {
                    "path": "api_set[2].value",
                    "label": "设定温度",
                    "value_type": "range",
                    "unit": "celsius",
                    "value_range": {"min": 16, "max": 31, "step": 0.5},
                    "user_value": None,
                }
            ],
        },
        {
            "step": 4,
            "c_brand": "米家冰箱Pro（餐厅）",
            "c_instance_id": "fridge-1",
            "e_name": "冷藏",
            "step_intent": "将冰箱设为速冷模式，加速冷却刚放入的饮料。",
            "param_placeholders": [
                {
                    "path": "api_set[1].value",
                    "label": "设定温度",
                    "value_type": "range",
                    "unit": "celsius",
                    "value_range": {"min": 2, "max": 8, "step": 1},
                    "user_value": None,
                }
            ],
        },
        {
            "step": 6,
            "c_brand": "米家洗衣机（洗手间）",
            "c_instance_id": "washer-1",
            "e_name": "洗衣",
            "step_intent": "洗涤衬衣。",
            "param_placeholders": [
                {
                    "path": "api_set[1].value",
                    "label": "模式",
                    "value_type": "enum",
                    "options": [
                        {"value": 15, "label_zh": "羊毛洗"},
                        {"value": 22, "label_zh": "冲锋衣"},
                    ],
                    "user_value": None,
                }
            ],
        },
    ]
    bind_plan_placeholders(steps, text)
    assert steps[0]["param_placeholders"][0]["user_value"] == "22"
    assert steps[1]["param_placeholders"][0]["user_value"] in (None, "")
    assert steps[2]["param_placeholders"][0]["user_value"] in (None, "")
    print("OK: temperature stays on the air conditioner")


def test_bind_plan_room_and_bare_number():
    text = "把客厅空调调到22"
    steps = [
        {
            "c_brand": "客厅空调",
            "c_instance_id": "ac-live",
            "e_name": "制冷",
            "step_intent": "开启客厅空调制冷。",
            "param_placeholders": [
                {
                    "path": "api_set[0].value",
                    "label": "设定温度",
                    "value_type": "range",
                    "unit": "celsius",
                    "value_range": {"min": 16, "max": 31},
                    "user_value": None,
                }
            ],
        },
        {
            "c_brand": "卧室空调",
            "c_instance_id": "ac-bed",
            "e_name": "制冷",
            "step_intent": "开启卧室空调制冷。",
            "param_placeholders": [
                {
                    "path": "api_set[0].value",
                    "label": "设定温度",
                    "value_type": "range",
                    "unit": "celsius",
                    "value_range": {"min": 16, "max": 31},
                    "user_value": None,
                }
            ],
        },
    ]
    bind_plan_placeholders(steps, text)
    assert steps[0]["param_placeholders"][0]["user_value"] == "22"
    assert steps[1]["param_placeholders"][0]["user_value"] in (None, "")
    print("OK: bare number follows the room")


def test_annotate_device_env_match():
    devices = [
        {"c_instance_id": "ac-1", "env_set": [1], "weight": 1},
        {"c_instance_id": "fan-1", "env_set": [], "weight": 5},
    ]
    annotate_device_env_match(
        "把房间调凉快",
        devices,
        [{"env_id": 1, "match_key": "air_temperature", "env_name": "室内气温"}],
    )
    assert devices[0]["env_match_score"] == 1
    assert devices[1]["env_match_score"] == 0
    print("OK: env match")


_ENV_MAPS = [
    {"env_id": 17, "match_key": "air_temperature", "env_name": "室内气温", "aliases": ["室温", "室内温度"]},
    {"env_id": 18, "match_key": "air_exchange", "env_name": "通风换气量", "aliases": []},
]


def test_hinted_keys_skip_bare_degree():
    dehumid = hinted_env_match_keys("帮我除湿", _ENV_MAPS)
    assert "air_humidity" in dehumid
    assert "air_temperature" not in dehumid
    room = hinted_env_match_keys("室温太高了", _ENV_MAPS)
    assert "air_temperature" in room
    print("OK: hinted keys skip bare 度")


def test_combo_pre_rank_cooling():
    text = "凉快一点"
    wanted = hinted_env_match_keys(text, _ENV_MAPS)
    scores = {}
    for eid in (1, 16, 12):
        combo = resolve_effect_combo(eid, _ENV_MAPS)
        scores[eid] = combo_intent_score(combo, wanted, text)[0]
    assert scores[1] > scores[16]
    assert scores[1] > scores[12]
    print("OK: combo pre-rank cooling")


def test_l4_wanted_from_l3_primary():
    wanted_ids, wanted_keys, labels = wanted_env_from_effect_ids({1}, _ENV_MAPS)
    assert "air_temperature" in wanted_keys
    assert "室内气温" in labels
    devices = [
        {"c_instance_id": "ac-1", "env_set": [17], "weight": 1},
        {"c_instance_id": "fan-1", "env_set": [], "weight": 5},
    ]
    annotate_device_env_match(
        "凉快一点",
        devices,
        _ENV_MAPS,
        wanted_keys=wanted_keys,
        wanted_env_ids=wanted_ids,
    )
    assert devices[0]["env_match_score"] >= 2
    assert devices[1]["env_match_score"] == 0
    print("OK: l4 wanted from l3")


def test_l5_env_ranks_cooling_recipe():
    cool = _effect(
        "空调：制冷",
        e_id=1,
        c_instance_id="ac-1",
        param_schema=None,
        api_set=[{"op": "cool"}],
        env_impact=[17],
    )
    vent = _effect(
        "空调：开新风",
        e_id=16,
        c_instance_id="ac-1",
        param_schema=None,
        api_set=[{"op": "fan"}],
        env_impact=[18],
    )
    read = _effect(
        "空调：读温度",
        e_id=12,
        c_instance_id="ac-1",
        param_schema=None,
        api_set=[{"op": "read"}],
        env_impact=[17],
    )
    recipes = [
        {
            "recipe_uid": "空调：制冷",
            "c_instance_id": "ac-1",
            "recipe_name": "制冷",
            "covers_effects": [1],
            "steps": [{"uid": cool["uid"], "role": "effect"}],
            "extra": {},
        }
    ]
    cands = compose_l5_candidates(
        payloads=[cool, vent, read],
        recipes=recipes,
        pref_by_uid={
            cool["uid"]: {"weight": 1},
            vent["uid"]: {"weight": 3},
            read["uid"]: {"weight": 2},
        },
        device_pref_by_id={"ac-1": {"weight": 1}},
        selected_e_ids={1, 12, 16},
        filter_by_l3=False,
        effect_name_map={1: "制冷", 12: "温度数据获取", 16: "通风换气"},
        device_brand_map={"ac-1": "测试空调"},
        intent_text="凉快一点",
        wanted_env_ids={17},
        env_name_by_id={17: "室内气温", 18: "通风换气量"},
    )
    assert cands
    assert cands[0]["candidate_kind"] == "recipe"
    assert cands[0]["e_id"] == 1
    assert cands[0]["env_match_score"] >= 1
    print("OK: l5 env ranks cooling recipe")


if __name__ == "__main__":
    test_remap_api_set_path()
    test_merge_recipe_optional_slots()
    test_drop_subset_recipes()
    test_compose_recipe_hides_lazy_and_attaches_params()
    test_lazy_weight_inherits_to_generic_recipe()
    test_filter_l3_drops_unrelated_recipe()
    test_fallback_atom_attaches_supports_e_ids()
    test_reachable_includes_parameter_supports()
    test_pref_eligible_skips_lazy_and_parameter()
    test_strategy_named_gate_for_l5()
    test_bind_placeholders_from_intent()
    test_bind_plan_does_not_spray_temperature()
    test_bind_plan_room_and_bare_number()
    test_annotate_device_env_match()
    test_hinted_keys_skip_bare_degree()
    test_combo_pre_rank_cooling()
    test_l4_wanted_from_l3_primary()
    test_l5_env_ranks_cooling_recipe()
    print("All intent compose tests passed")
