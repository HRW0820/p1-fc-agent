"""W1 Session 3 · Pydantic 进阶的测试规格（TDD：先红后绿）

任务：在 src/p1_fc_agent/tools.py 中升级 WeatherQuery、新建 PopulationQuery / CalcQuery，
并实现 format_validation_error / run_calculator 两个函数。

本文件 8 个测试 + 上一节的 7 个测试最终要 15 个全绿。
注意：升级 WeatherQuery（加 extra="forbid" 和 city 校验器）后，
旧的 test_tools.py 必须仍然全绿——这本身就是一条规格（向后兼容）。
"""
import pytest
from pydantic import ValidationError

from p1_fc_agent.tools import (
    CalcQuery,
    PopulationQuery,
    WeatherQuery,
    format_validation_error,
    run_calculator,
)


# ---------- 1. Field 约束 ----------

def test_population_only_asks_for_city():
    """W4-S1 改：人口数不让模型填（P018），参数表里只剩 city；多填的 value 被拒收。"""
    assert PopulationQuery(city="北京").city == "北京"

    with pytest.raises(ValidationError) as exc:
        PopulationQuery(city="北京", value=2189)
    assert exc.value.errors()[0]["type"] == "extra_forbidden"


# ---------- 2. min_length + 字符集校验器 ----------

def test_calc_expression_not_empty():
    """空表达式直接拒收（string_too_short）。"""
    with pytest.raises(ValidationError) as exc:
        CalcQuery(expression="")
    assert exc.value.errors()[0]["type"] == "string_too_short"


def test_calc_expression_charset():
    """字符集海关：只放行数字和运算符，'import os' 这类必须死在门口。"""
    with pytest.raises(ValidationError):
        CalcQuery(expression="import os")
    with pytest.raises(ValidationError):
        CalcQuery(expression="__import__('os')")

    q = CalcQuery(expression="20 - 12")
    assert q.expression == "20 - 12"


# ---------- 3. field_validator：清洗 + 空白拒收 ----------

def test_city_stripped():
    """'  北京  ' 清洗成 '北京'（善意修剪）。"""
    q = WeatherQuery(city="  北京  ")
    assert q.city == "北京"


def test_city_blank_rejected():
    """'' 和 '   ' 拒收（空白不是城市名）。"""
    with pytest.raises(ValidationError):
        WeatherQuery(city="")
    with pytest.raises(ValidationError):
        WeatherQuery(city="   ")


# ---------- 4. extra="forbid"：对夹带报警 ----------

def test_extra_forbidden():
    """上一节思考题3的解药：多传 hobby 直接抛错。"""
    with pytest.raises(ValidationError) as exc:
        WeatherQuery.model_validate({"city": "北京", "hobby": "钓鱼"})
    err = exc.value.errors()[0]
    assert err["type"] == "extra_forbidden"
    assert err["loc"] == ("hobby",)


# ---------- 5. 错误喂回模式（本节核心架构） ----------

def test_format_validation_error():
    """ValidationError → 一句话，含字段名和原因，可直接喂回模型。"""
    try:
        WeatherQuery.model_validate({"city": None})
        raise AssertionError("应该抛 ValidationError")
    except ValidationError as e:
        msg = format_validation_error(e)
        assert isinstance(msg, str)
        assert "city" in msg                 # 字段名在
        assert len(msg) > 10                 # 不是空壳


def test_run_calculator_gate():
    """海关写法：永不 raise——合法则返回结果，非法则返回错误文本。"""
    # 合法输入：返回计算结果
    assert run_calculator("20 - 12") == "8"
    assert run_calculator("2 * (3 + 4)") == "14"

    # 非法输入：不炸，返回可喂回模型的错误文本（含字段名）
    out1 = run_calculator("")
    assert "expression" in out1
    out2 = run_calculator("import os")
    assert "expression" in out2

    # 旧测试兼容性自查（同规格的另一面）
    assert set(WeatherQuery(city="北京").model_dump().keys()) == {"city", "unit"}
