from effect_env_combos import (
    COMBOS,
    EFFECT_META,
    inverted_links,
    hang_effect_priors_by_key,
    related_ids_for_key,
)
from env_catalog import catalog_as_env_rows


def _row(match_key: str) -> dict:
    for row in catalog_as_env_rows():
        if row.get("match_key") == match_key:
            return row
    raise AssertionError(f"missing catalog row {match_key}")


def test_all_effects_have_combos():
    missing = [eid for eid in EFFECT_META if eid not in COMBOS]
    extra = [eid for eid in COMBOS if eid not in EFFECT_META]
    assert not missing, missing
    assert not extra, extra
    assert len(COMBOS) == 64


def test_air_circulation_not_ventilation():
    o_ids, e_ids = related_ids_for_key("air_circulation", [], [])
    assert 16 not in e_ids
    assert 12 not in e_ids
    assert set(e_ids) == {1, 11}
    assert o_ids == [1]
    priors = hang_effect_priors_by_key()
    assert "air_circulation" not in priors
    row = _row("air_circulation")
    assert 16 not in row["related_e_ids"]


def test_wash_state_not_personal_care():
    _, e_ids = related_ids_for_key("wash_state", [], [])
    assert 21 not in e_ids
    assert set(e_ids) == {19, 30}


def test_noise_not_air_quality():
    _, e_ids = related_ids_for_key("noise_level", [], [])
    assert 18 not in e_ids
    assert 47 not in e_ids


def test_water_temp_not_purifier():
    _, e_ids = related_ids_for_key("water_temperature", [], [])
    assert 27 not in e_ids
    assert 28 in e_ids


def test_opening_state_includes_door():
    _, e_ids = related_ids_for_key("opening_state", [], [])
    assert set(e_ids) >= {2, 10, 44}


def test_video_feed_not_display():
    _, e_ids = related_ids_for_key("video_feed", [], [])
    assert 49 not in e_ids
    assert set(e_ids) == {4, 5}


def test_convertible_and_cleanliness_not_default_effects():
    links = inverted_links()
    assert links["convertible_temperature"]["e_ids"] == []
    assert links["cleanliness_state"]["e_ids"] == []


def test_humidity_hang_priors_include_humidify():
    priors = hang_effect_priors_by_key()
    assert set(priors["air_humidity"]) == {"除湿", "加湿"}
    assert set(priors["air_exchange"]) == {"通风换气"}
    assert "辅助工作" in priors["wash_state"]
    assert "洗衣" in priors["wash_state"]
    assert "convertible_temperature" not in priors


if __name__ == "__main__":
    test_all_effects_have_combos()
    test_air_circulation_not_ventilation()
    test_wash_state_not_personal_care()
    test_noise_not_air_quality()
    test_water_temp_not_purifier()
    test_opening_state_includes_door()
    test_video_feed_not_display()
    test_convertible_and_cleanliness_not_default_effects()
    test_humidity_hang_priors_include_humidify()
    print("ALL effect env combo tests passed")
