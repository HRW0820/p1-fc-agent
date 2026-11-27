"""Function Calling：把几张表格写成说明书递给模型，让它自己挑一张填"""
import json

from pydantic import ValidationError

from p1_fc_agent import llm
from p1_fc_agent.structured import ParseError
from p1_fc_agent.tools import CalcQuery, WeatherQuery, format_validation_error, run_calculator


def tool_spec(model) -> dict:
    """一张表格变成 API 认的说明书：叫什么、收哪些参数（JSON Schema 由 Pydantic 现生成）"""
    schema = model.model_json_schema()
    return {"type": "function", "function": {"name": model.__name__, "description": model.__doc__ or "",
                                             "parameters": schema}}


def read_call(call: dict, models: list):
    """模型递回来的一次调用：找到对应的表格，把参数填进去过安检"""
    name = call["function"]["name"]                       # 两层：先 function 再 name
    model = {m.__name__: m for m in models}.get(name)     # 表格名 → 表格；找不到就是 None
    if model is None:
        raise ParseError(f"模型调了一个不存在的工具：{name}")
    try:
        data = json.loads(call["function"]["arguments"])  # arguments 是一段 JSON 文本，不是字典
        return model.model_validate(data)                 # W1 的安检机：W3-S2 的第二道关，原样搬过来
    except ValidationError as e:
        raise ParseError(f"工具 {name} 的参数不对：{format_validation_error(e)}") from e
    except json.JSONDecodeError as e:
        raise ParseError(f"工具 {name} 的参数不是合法的 JSON：{e.msg}") from e


async def decide(question: str, models: list, **options) -> list:
    """让模型自己挑表格，返回填好的表格列表（按模型递出来的顺序）。一张都没挑时是空列表"""
    tools = [tool_spec(m) for m in models]
    _, _, _, calls = await llm.chat([{"role": "user", "content": question}], tools=tools, **options)
    return [read_call(call, models) for call in calls]


def run(query) -> str:
    """执行一张填好的表格，返回一段文字。今天只有计算器是真的，天气和人口先放假话"""
    if isinstance(query, CalcQuery):
        return run_calculator(query.expression)
    if isinstance(query, WeatherQuery):
        return f"{query.city}今天晴，12{'°C' if query.unit == 'celsius' else '°F'}"
    return f"{query.city}人口约 2487 万"


async def ask(question: str, models: list, **options) -> str:
    """完整一轮：模型挑表 → 执行 → 结果递回去 → 模型总结。回的是模型最后说的那段话"""
    messages = [{"role": "user", "content": question}]
    tools = [tool_spec(m) for m in models]
    content, _, _, calls = await llm.chat(messages, tools=tools, **options)
    if not calls:                                   # 模型觉得不用调工具，直接说话了（比如问"你好"）
        return content
    messages.append({"role": "assistant", "content": content, "tool_calls": calls})   # 原样抄回它刚才的话
    for call, form in zip(calls, [read_call(c, models) for c in calls]):
        messages.append({"role": "tool", "tool_call_id": call["id"], "content": run(form)})
    text, _, _, _ = await llm.chat(messages, **options)   # 第二次不带 tools：这次只要它总结
    return text
