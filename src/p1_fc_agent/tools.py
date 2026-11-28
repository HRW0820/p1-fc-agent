from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from typing import Literal

_CALC_CHARS = set("0123456789+-*/(). ")

class CityForm(BaseModel):
    """两张都要填城市名的表共用的表头"""
    model_config = ConfigDict(extra="forbid")         # 多填一格就拒收，不让模型夹带字段
    city: str = Field(description="城市名，用中文，不带「市」字，例如：北京、上海")

    @field_validator("city")
    @classmethod
    def clean_city(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("城市名不能为空白")
        return v


class WeatherQuery(CityForm):
    """查一个城市今天的天气和气温。客人问天气、气温、冷热、温差时用；问人口请用 PopulationQuery"""
    unit: Literal["celsius", "fahrenheit"] = "celsius"   # 可选：客人没说单位就是摄氏；枚举：只认这两个词


class DateRange(BaseModel):
    start: str
    end: str


class TripQuery(BaseModel):
    origin: str
    destination: str
    date_range: DateRange


class PopulationQuery(CityForm):
    """查一个城市的常住人口。客人问人口、有多少人时用；问天气请用 WeatherQuery"""


class CalcQuery(BaseModel):
    """做一步四则运算。两个数要相加、相减、相乘、相除时都用它，不要自己心算"""
    model_config = ConfigDict(extra="forbid")         # 以前没有这行：模型多填的字段会被悄悄丢掉
    expression: str = Field(min_length=1, description="一条算式，只含数字、空格和 + - * / ( )，例如：20-12")

    @field_validator("expression")
    @classmethod
    def charset(cls, v: str) -> str:
        if not set(v) <= _CALC_CHARS:
            raise ValueError("表达式含有非法字符")
        return v


def format_validation_error(e: ValidationError) -> str:
    parts = []
    for err in e.errors():
        loc = ".".join(str(x) for x in err["loc"])
        parts.append(f"{loc}: {err['msg']}")
    return "参数校验失败: " + "; ".join(parts)


def run_calculator(expression: str) -> str:
    try:
        q = CalcQuery(expression=expression)
        return str(eval(q.expression))  # 字符集校验后的教学用求值；生产环境应改用 ast
    except ValidationError as e:
        return format_validation_error(e)
    except Exception as e:
        return f"工具执行失败: expression: {e}"
