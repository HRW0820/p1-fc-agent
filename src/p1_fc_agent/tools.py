from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

_CALC_CHARS = set("0123456789+-*/(). ")


class WeatherQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city: str
    unit: str = "celsius"

    @field_validator("city")
    @classmethod
    def clean_city(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("城市名不能为空白")
        return v


class DateRange(BaseModel):
    start: str
    end: str


class TripQuery(BaseModel):
    origin: str
    destination: str
    date_range: DateRange


class PopulationQuery(BaseModel):
    city: str
    value: int = Field(gt=0, description="城市人口数，必须为正")


class CalcQuery(BaseModel):
    expression: str = Field(min_length=1, description="只含数字和四则运算符的表达式")

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
