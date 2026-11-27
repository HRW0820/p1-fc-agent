"""W3-S3 规格：p1_fc_agent.calling —— Function Calling 核心（12 条，没有一条花过钱）。

要做什么：
1. llm.chat：加 tools 参数（不带时请求体和以前一样），返回四样，第四样是 tool_calls（没有就是空列表）
2. tool_spec：一张 Pydantic 表格变成 API 认的工具说明书
3. read_call：一次调用变成填好的表格；工具不存在、参数不是 JSON、参数填错，都报 ParseError
4. decide：让模型挑表格，回填好的表格列表（一张都没挑时是空列表）
5. run + ask：执行 → 用 role="tool" 递回去 → 模型总结；模型没调工具时直接回它说的话

先红后绿的步骤见讲义 W3-讲义-3 第二节。
"""

import asyncio

import pytest

from p1_fc_agent import llm
from p1_fc_agent import calling
from p1_fc_agent.calling import ParseError
from p1_fc_agent.tools import CalcQuery, PopulationQuery, WeatherQuery

TOOLS = [WeatherQuery, CalcQuery, PopulationQuery]
TOOL = {"type": "function", "function": {"name": "WeatherQuery", "parameters": {"type": "object"}}}
MESSAGES = [{"role": "user", "content": "上海天气怎么样"}]


def call(name, arguments, id="call_1"):
    """模型递回来的一次调用，长 API 回执里的样子"""
    return {"id": id, "type": "function", "function": {"name": name, "arguments": arguments}}


class FakeSend:
    """按顺序回放假回复。每条回复是 (模型说的话, tool_calls)"""

    def __init__(self, *replies):
        self.replies = replies
        self.payloads = []

    async def __call__(self, payload):
        self.payloads.append(payload)
        content, tool_calls = self.replies[len(self.payloads) - 1]
        return {"choices": [{"finish_reason": "tool_calls" if tool_calls else "stop",
                             "message": {"role": "assistant", "content": content, "tool_calls": tool_calls}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1}}


def test_chat_sends_tools_only_when_given():
    fake = FakeSend(("", []), ("", []))
    asyncio.run(llm.chat(MESSAGES, send=fake, tools=[TOOL]))
    assert fake.payloads[0]["tools"] == [TOOL]
    asyncio.run(llm.chat(MESSAGES, send=fake))
    assert "tools" not in fake.payloads[1]


def test_chat_returns_tool_calls():
    calls = [call("WeatherQuery", '{"city": "上海"}')]
    fake = FakeSend(("", calls), ("你好！", None))
    assert asyncio.run(llm.chat(MESSAGES, send=fake))[3] == calls
    assert asyncio.run(llm.chat(MESSAGES, send=fake))[3] == []       # 回执里没有 tool_calls 时是空列表


def test_tool_spec_has_name_description_and_schema():
    spec = calling.tool_spec(WeatherQuery)
    assert spec == {"type": "function", "function": {"name": "WeatherQuery", "description": "",
                                                     "parameters": WeatherQuery.model_json_schema()}}


def test_read_call_returns_filled_form():
    assert calling.read_call(call("WeatherQuery", '{"city": " 上海 "}'), TOOLS) == WeatherQuery(city="上海")


def test_read_call_unknown_tool_raises():
    with pytest.raises(ParseError, match="不存在的工具：TripQuery"):
        calling.read_call(call("TripQuery", "{}"), TOOLS)


def test_read_call_bad_json_raises():
    with pytest.raises(ParseError, match="CalcQuery 的参数不是合法的 JSON"):
        calling.read_call(call("CalcQuery", "3 * 7"), TOOLS)


def test_read_call_invalid_fields_raises():
    with pytest.raises(ParseError, match="WeatherQuery 的参数不对：参数校验失败: city"):
        calling.read_call(call("WeatherQuery", '{"city": ""}'), TOOLS)


def test_decide_returns_filled_forms_in_order():
    calls = [call("WeatherQuery", '{"city": "上海"}'), call("CalcQuery", '{"expression": "3*7"}', "call_2")]
    fake = FakeSend(("", calls))
    forms = asyncio.run(calling.decide("上海天气怎么样？另外三乘以七", TOOLS, send=fake, max_tokens=10))
    assert forms == [WeatherQuery(city="上海"), CalcQuery(expression="3*7")]
    assert [t["function"]["name"] for t in fake.payloads[0]["tools"]] == ["WeatherQuery", "CalcQuery", "PopulationQuery"]
    assert fake.payloads[0]["max_tokens"] == 10


def test_decide_without_calls_returns_empty_list():
    fake = FakeSend(("你好！", []))
    assert asyncio.run(calling.decide("你好", TOOLS, send=fake)) == []


def test_run_executes_calculator_for_real():
    assert calling.run(CalcQuery(expression="2+3*4")) == "14"
    assert "上海" in calling.run(WeatherQuery(city="上海"))


def test_ask_feeds_results_back_as_tool_messages():
    fake = FakeSend(("", [call("CalcQuery", '{"expression": "3*7"}')]), ("21", []))
    assert asyncio.run(calling.ask("三乘以七等于多少", TOOLS, send=fake)) == "21"
    user, assistant, tool = fake.payloads[1]["messages"]
    assert assistant["tool_calls"][0]["id"] == "call_1"
    assert tool == {"role": "tool", "tool_call_id": "call_1", "content": "21"}
    assert "tools" not in fake.payloads[1]


def test_ask_answers_directly_when_no_tool_is_called():
    fake = FakeSend(("你好！", []))
    assert asyncio.run(calling.ask("你好", TOOLS, send=fake)) == "你好！"
    assert len(fake.payloads) == 1                              # 没调工具就只打一次电话
