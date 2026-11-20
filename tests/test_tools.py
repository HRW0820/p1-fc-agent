"""W1 Session 2 · Pydantic 基础的测试规格（TDD：先红后绿）

你的任务：新建 src/p1_fc_agent/tools.py，实现 WeatherQuery / DateRange / TripQuery，
让本文件 7 个测试全绿。测试即合同——每个 test_ 的名字和断言就是需求说明。
"""
import pytest
from pydantic import ValidationError

from p1_fc_agent.tools import DateRange, TripQuery, WeatherQuery


def test_weather_basic():
    """基本字段 + 默认值：city 必填，unit 默认 'celsius'。"""
    q = WeatherQuery(city="北京")
    assert q.city == "北京"
    assert q.unit == "celsius"

    q2 = WeatherQuery(city="上海", unit="fahrenheit")
    assert q2.unit == "fahrenheit"


def test_missing_city():
    """必填字段缺失 → ValidationError。"""
    with pytest.raises(ValidationError):
        WeatherQuery()


def test_none_city():
    """None 不是合法 str → ValidationError（注意：123 会'转换'成 '123'，None 不会）。"""
    with pytest.raises(ValidationError):
        WeatherQuery(city=None)


def test_weather_dump():
    """model_dump() 返回 dict，键集合与字段一致。"""
    q = WeatherQuery(city="北京")
    d = q.model_dump()
    assert isinstance(d, dict)
    assert set(d.keys()) == {"city", "unit"}
    assert d["city"] == "北京"


def test_weather_validate_roundtrip():
    """model_validate：从（不可信的）dict 重建模型，dump 后不变量成立。"""
    raw = {"city": "深圳", "unit": "fahrenheit"}
    q = WeatherQuery.model_validate(raw)
    assert q.city == "深圳"
    assert q.model_dump() == raw


def test_nested_date_range():
    """嵌套模型：外层合法、内层坏数据，一样被拦。"""
    # 合法的完整旅行查询
    ok = TripQuery(
        origin="北京",
        destination="上海",
        date_range=DateRange(start="2026-12-01", end="2026-12-05"),
    )
    assert ok.date_range.start == "2026-12-01"

    # 内层坏数据（start=None）→ 整体 ValidationError
    with pytest.raises(ValidationError):
        TripQuery(
            origin="北京",
            destination="上海",
            date_range=DateRange(start=None, end="2026-12-05"),
        )


def test_validation_error_is_structured():
    """ValidationError.errors() 是结构化列表：loc 定位字段，可编程处理。"""
    try:
        WeatherQuery(city=None)
        raise AssertionError("应该抛 ValidationError 才对")
    except ValidationError as e:
        errs = e.errors()
        assert isinstance(errs, list)
        first = errs[0]
        assert first["loc"][0] == "city"      # loc 是元组，第一个元素是字段名
        assert first["type"] == "string_type"  # Pydantic 2：None 传给 str 的类型码
