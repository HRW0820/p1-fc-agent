"""W4-S1 规格：p1_fc_agent.tools 的三张表格 + calling.run 的人口账本（10 条，没有一条花过钱）。

要做什么：
1. CityForm：两张要填城市名的表共用的表头（city 必填、带说明、去空白、多填拒收）
2. WeatherQuery：类文档字符串写"什么时候用"；unit 改成枚举 celsius / fahrenheit，可选
3. PopulationQuery：只留 city，不再让模型填人口数（P018）
4. CalcQuery：类文档字符串 + expression 的说明写清楚收什么
5. calling.run：人口查一本假账本，查不到说"未知城市"（P019）；天气按 unit 换算

先红后绿的步骤见讲义 W4-讲义-1 第二节。
"""

import pytest
from pydantic import ValidationError

from p1_fc_agent import calling
from p1_fc_agent import tools

TOOLS = [tools.WeatherQuery, tools.CalcQuery, tools.PopulationQuery]


def spec(model) -> dict:
    """模型看到的那页说明书"""
    return calling.tool_spec(model)["function"]


# ---------- CityForm + WeatherQuery：说明书、必填和可选、枚举 ----------

def test_weather_description_says_when_to_use_it():
    text = spec(tools.WeatherQuery)["description"]
    assert "天气" in text                                        # 讲清什么时候用它
    assert "PopulationQuery" in text                             # 并给"不该用它的时候该用谁"指路


def test_city_is_required_and_unit_is_optional():
    schema = tools.WeatherQuery.model_json_schema()
    assert schema["required"] == ["city"]                        # 没说单位的客人不用填 unit
    assert schema["properties"]["unit"]["default"] == "celsius"
    assert schema["properties"]["unit"]["enum"] == ["celsius", "fahrenheit"]


def test_city_field_tells_the_model_what_to_write():
    assert "城市" in tools.WeatherQuery.model_json_schema()["properties"]["city"]["description"]
    assert tools.WeatherQuery(city="  北京  ").city == "北京"     # 表头里的清洗：W1 的老规矩还在


def test_unit_rejects_any_other_word():
    with pytest.raises(ValidationError) as exc:
        tools.WeatherQuery(city="北京", unit="华氏")
    assert exc.value.errors()[0]["type"] == "literal_error"
    assert tools.WeatherQuery(city="北京").unit == "celsius"      # 不填就是摄氏


# ---------- PopulationQuery：参数表里只留"查什么"（P018） ----------

def test_population_form_only_asks_for_the_city():
    assert set(tools.PopulationQuery.model_json_schema()["properties"]) == {"city"}
    with pytest.raises(ValidationError) as exc:
        tools.PopulationQuery(city="上海", value=24870000)        # 模型还想填人口数：拒收
    assert exc.value.errors()[0]["type"] == "extra_forbidden"


def test_population_form_shares_the_city_header():
    assert tools.PopulationQuery(city=" 上海 ") == tools.PopulationQuery(city="上海")
    assert "人口" in spec(tools.PopulationQuery)["description"]


# ---------- CalcQuery ----------

def test_calc_description_tells_the_model_what_to_send():
    assert "运算" in spec(tools.CalcQuery)["description"]
    assert "算式" in tools.CalcQuery.model_json_schema()["properties"]["expression"]["description"]


def test_every_tool_has_a_description():
    assert all(spec(m)["description"] for m in TOOLS)             # 三页说明书没有一页是空白的


# ---------- calling.run：人口账本（P019）+ 单位换算 ----------

def test_run_population_looks_up_a_fake_ledger():
    assert calling.run(tools.PopulationQuery(city="上海")) == "上海常住人口约 2487 万"
    assert calling.run(tools.PopulationQuery(city="深圳")) == "未知城市：深圳"


def test_run_weather_converts_to_fahrenheit_when_asked():
    assert calling.run(tools.WeatherQuery(city="北京")) == "北京今天晴，12°C"
    assert calling.run(tools.WeatherQuery(city="北京", unit="fahrenheit")) == "北京今天晴，53.6°F"
