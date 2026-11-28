"""W3-S4 规格：p1_fc_agent.fc_loop —— FC 版 ReAct 循环（13 条，没有一条花过钱）。

要做什么：
1. execute：模型递回来的一张卡 → 填表、执行，回 (工具名, 结果文字)；卡填错了不抛，把原因当结果
2. react_events：循环本体。一轮 = 问模型一次 + 把它递的卡挨个执行、递回去；没递卡就是最终回答
3. run_react：整箱拿，只要最后那句回答
4. calling.run：天气换一本假账本（北京 12、上海 20、广州 25），别的城市回"未知城市"

先红后绿的步骤见讲义 W3-讲义-4 第二节。
"""

import asyncio

from p1_fc_agent import calling
from p1_fc_agent import fc_loop
from p1_fc_agent.tools import CalcQuery, PopulationQuery, WeatherQuery

TOOLS = [WeatherQuery, CalcQuery, PopulationQuery]
QUESTION = "北京和上海今天的气温相差多少度？"
FINAL = "北京和上海今天的气温相差 8 度。"


def call(name, arguments, id="call_1"):
    """模型递回来的一次调用，长 API 回执里的样子"""
    return {"id": id, "type": "function", "function": {"name": name, "arguments": arguments}}


BEIJING = call("WeatherQuery", '{"city": "北京"}', "call_a")
SHANGHAI = call("WeatherQuery", '{"city": "上海"}', "call_b")
DIFF = call("CalcQuery", '{"expression": "20-12"}', "call_c")


class FakeSend:
    """按顺序回放假回复。每条回复是 (模型说的话, tool_calls)"""

    def __init__(self, *replies):
        self.replies = replies
        self.payloads = []
        self.sizes = []                # 每次被调用时对话有几条（payload 里存的是同一个列表，事后看全是最终的长度）

    async def __call__(self, payload):
        self.payloads.append(payload)
        self.sizes.append(len(payload["messages"]))
        content, tool_calls = self.replies[len(self.payloads) - 1]
        return {"choices": [{"finish_reason": "tool_calls" if tool_calls else "stop",
                             "message": {"role": "assistant", "content": content, "tool_calls": tool_calls}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1}}


def scripted():
    """剧本：一轮一张卡，查北京 → 查上海 → 算差 → 回答"""
    return FakeSend(("", [BEIJING]), ("", [SHANGHAI]), ("", [DIFF]), (FINAL, []))


def collect(question=QUESTION, fake=None, **options):
    """把循环吐出的每一条收进列表（run_react 是整箱拿，这个要的是每一条）"""

    async def listen():
        return [event async for event in fc_loop.react_events(question, TOOLS, send=fake or scripted(), **options)]

    return asyncio.run(listen())


# ---------- execute：一张卡 ----------

def test_execute_runs_a_well_filled_form():
    assert fc_loop.execute(DIFF, TOOLS) == ("CalcQuery", "8")


def test_execute_bad_arguments_become_the_observation():
    name, text = fc_loop.execute(call("WeatherQuery", '{"city": ""}'), TOOLS)
    assert name == "WeatherQuery"
    assert text.startswith("工具 WeatherQuery 的参数不对")


def test_execute_unknown_tool_becomes_the_observation():
    assert fc_loop.execute(call("TripQuery", "{}"), TOOLS) == ("TripQuery", "模型调了一个不存在的工具：TripQuery")


# ---------- react_events：循环本体 ----------

def test_trace_for_one_card_per_round():
    events = collect()
    assert events == [
        {"type": "step", "step": 1, "text": ""},
        {"type": "observation", "step": 1, "tool": "WeatherQuery", "text": "北京今天晴，12°C"},
        {"type": "step", "step": 2, "text": ""},
        {"type": "observation", "step": 2, "tool": "WeatherQuery", "text": "上海今天晴，20°C"},
        {"type": "step", "step": 3, "text": ""},
        {"type": "observation", "step": 3, "tool": "CalcQuery", "text": "8"},
        {"type": "step", "step": 4, "text": FINAL},
        {"type": "final", "step": 4, "text": FINAL},
    ]


def test_two_cards_in_one_round_are_executed_in_order():
    fake = FakeSend(("", [BEIJING, SHANGHAI]), ("", [DIFF]), (FINAL, []))
    events = collect(fake=fake)
    assert [e["step"] for e in events] == [1, 1, 1, 2, 2, 3, 3]
    assert events[2] == {"type": "observation", "step": 1, "tool": "WeatherQuery", "text": "上海今天晴，20°C"}
    assert events[-1]["type"] == "final"


def test_tool_results_go_back_as_tool_messages():
    fake = FakeSend(("", [BEIJING, SHANGHAI]), (FINAL, []))
    asyncio.run(fc_loop.run_react(QUESTION, TOOLS, send=fake))
    user, assistant, first, second = fake.payloads[1]["messages"]
    assert assistant["tool_calls"] == [BEIJING, SHANGHAI]
    assert first == {"role": "tool", "tool_call_id": "call_a", "content": "北京今天晴，12°C"}
    assert second["tool_call_id"] == "call_b" and second["content"] == "上海今天晴，20°C"


def test_conversation_grows_every_round():
    fake = scripted()
    asyncio.run(fc_loop.run_react(QUESTION, TOOLS, send=fake))
    assert fake.sizes == [1, 3, 5, 7]


def test_tools_are_sent_every_round():
    fake = scripted()
    asyncio.run(fc_loop.run_react(QUESTION, TOOLS, send=fake))
    for payload in fake.payloads:
        assert [t["function"]["name"] for t in payload["tools"]] == ["WeatherQuery", "CalcQuery", "PopulationQuery"]


def test_answers_directly_when_no_card_is_returned():
    fake = FakeSend(("你好！", []))
    events = collect("你好", fake=fake)
    assert events == [{"type": "step", "step": 1, "text": "你好！"},
                      {"type": "final", "step": 1, "text": "你好！"}]
    assert len(fake.payloads) == 1                              # 没递卡就只问了一次


def test_bad_card_is_fed_back_and_model_recovers():
    fake = FakeSend(("", [call("WeatherQuery", '{"city": ""}', "call_x")]), ("", [SHANGHAI]), (FINAL, []))
    events = collect(fake=fake)
    assert events[1]["text"].startswith("工具 WeatherQuery 的参数不对")
    fed_back = fake.payloads[1]["messages"][2]         # 第 3 条：用户、它自己的话、递回去的结果
    assert fed_back == {"role": "tool", "tool_call_id": "call_x", "content": events[1]["text"]}
    assert events[-1]["text"] == FINAL


def test_max_steps_fuse():
    fake = FakeSend(*[("", [DIFF])] * 8)
    events = collect(fake=fake, max_steps=3)
    assert [e["step"] for e in events if e["type"] == "step"] == [1, 2, 3]
    assert events[-1]["type"] == "final" and events[-1]["text"].startswith("[强制终止]")
    assert len(fake.payloads) == 3                              # 保险丝烧了就不再问模型
    assert fc_loop.MAX_STEPS == 8


# ---------- run_react：整箱拿 ----------

def test_run_react_returns_the_final_answer():
    assert asyncio.run(fc_loop.run_react(QUESTION, TOOLS, send=scripted())) == FINAL
    assert asyncio.run(fc_loop.run_react("你好", TOOLS, send=FakeSend(("你好！", [])))) == "你好！"


# ---------- calling.run：天气账本 ----------

def test_run_looks_up_a_fake_weather_db():
    assert calling.run(WeatherQuery(city="上海")) == "上海今天晴，20°C"
    assert calling.run(WeatherQuery(city="北京")) == "北京今天晴，12°C"
    assert calling.run(WeatherQuery(city="深圳")) == "未知城市：深圳"
