"""W3 周末规格：p1_fc_agent.budget —— 单次会话的账本（12 条，没有一条花过钱）。

要做什么：
1. Budget：一本会话账。charge(usage) 每打完一次电话记一笔（次数、输入输出 token、花了多少元），
   记完发现超过上限就抛 OverBudget
2. fc_loop.react_events 收一个 budget：钱超了就不再打下一次电话。模型这次递了卡就停，用账单代替答案；
   这次已经给出答案就照常交付（钱已经花了），但账要记全

先红后绿的两步见 W3 Day 7 笔记（这一课助手代做）。
"""

import asyncio

import pytest

from p1_fc_agent import budget
from p1_fc_agent import fc_loop
from p1_fc_agent import llm
from p1_fc_agent.tools import CalcQuery, PopulationQuery, WeatherQuery

TOOLS = [WeatherQuery, CalcQuery, PopulationQuery]
QUESTION = "北京和上海今天的气温相差多少度？"
FINAL = "北京和上海今天的气温相差 8 度。"


def usage(prompt, completion, hit=0):
    """一份像 DeepSeek 回执里的用量"""
    return {"prompt_tokens": prompt, "completion_tokens": completion, "prompt_cache_hit_tokens": hit}


def call(name, arguments, id="call_1"):
    """模型递回来的一次调用，长 API 回执里的样子"""
    return {"id": id, "type": "function", "function": {"name": name, "arguments": arguments}}


BEIJING = call("WeatherQuery", '{"city": "北京"}', "call_a")
U_ONE_YUAN = usage(1_000_000, 0)        # 按空闲价正好 1 元
U_60_CENTS = usage(600_000, 0)          # 正好 0.6 元


class CostedSend:
    """按顺序回放假回复，每条带一份用量：(模型说的话, tool_calls, 用量)"""

    def __init__(self, *replies):
        self.replies = replies
        self.count = 0

    async def __call__(self, payload):
        content, tool_calls, costed = self.replies[self.count]
        self.count += 1
        return {"choices": [{"finish_reason": "tool_calls" if tool_calls else "stop",
                             "message": {"role": "assistant", "content": content, "tool_calls": tool_calls}}],
                "usage": costed}


def collect(fake, **options):
    """把循环吐出的每一条收进列表"""

    async def listen():
        return [event async for event in fc_loop.react_events(QUESTION, TOOLS, send=fake, **options)]

    return asyncio.run(listen())


# ---------- Budget：记账 ----------

def test_budget_starts_with_an_empty_ledger():
    b = budget.Budget()
    assert (b.calls, b.prompt_tokens, b.completion_tokens, b.spent) == (0, 0, 0, 0.0)
    assert b.limit_yuan == 0.01


def test_charge_records_calls_tokens_and_money():
    b = budget.Budget(limit_yuan=10.0)
    b.charge(U_ONE_YUAN)
    b.charge(usage(0, 250))
    assert (b.calls, b.prompt_tokens, b.completion_tokens) == (2, 1_000_000, 250)
    assert b.spent == pytest.approx(1.001)


def test_charge_counts_cached_input_at_the_cheap_price():
    b = budget.Budget(limit_yuan=10.0)
    b.charge(usage(1_000_000, 1_000, hit=500_000))
    assert b.spent == pytest.approx(0.514)       # 50 万命中按 0.02、50 万未命中按 1.0、输出 1000 按 4.0


def test_budget_can_be_priced_at_the_peak_rate():
    peak = {name: price * 2 for name, price in llm.PRICE.items()}      # 高峰时段单价是空闲时段的两倍
    b = budget.Budget(limit_yuan=10.0, price=peak)
    b.charge(U_60_CENTS)
    assert b.spent == pytest.approx(1.2)


def test_spending_exactly_the_limit_does_not_raise():
    b = budget.Budget(limit_yuan=1.0)
    b.charge(U_ONE_YUAN)
    assert b.spent == pytest.approx(1.0)


def test_going_over_the_limit_raises_and_still_keeps_the_record():
    b = budget.Budget(limit_yuan=1.0)
    b.charge(U_ONE_YUAN)
    with pytest.raises(budget.OverBudget) as caught:
        b.charge(usage(0, 250))
    assert "已花 1.001000 元，超过上限 1.0 元" in str(caught.value)
    assert (b.calls, b.spent) == (2, pytest.approx(1.001))      # 超了的那一笔也记上：账要记全


def test_report_is_the_bill():
    b = budget.Budget(limit_yuan=10.0)
    b.charge(U_60_CENTS)
    assert b.report() == {"calls": 1, "prompt_tokens": 600_000, "completion_tokens": 0, "spent": 0.6}


# ---------- fc_loop.react_events：钱超了就停 ----------

def test_loop_without_a_budget_behaves_as_before():
    fake = CostedSend((FINAL, [], U_ONE_YUAN))
    assert collect(fake)[-1] == {"type": "final", "step": 1, "text": FINAL}


def test_loop_charges_every_call_including_the_last():
    fake = CostedSend(("", [BEIJING], U_60_CENTS), (FINAL, [], U_60_CENTS))
    b = budget.Budget(limit_yuan=10.0)
    assert collect(fake, budget=b)[-1]["text"] == FINAL
    assert b.report() == {"calls": 2, "prompt_tokens": 1_200_000, "completion_tokens": 0, "spent": 1.2}


def test_loop_stops_before_the_next_call_once_the_budget_is_blown():
    fake = CostedSend(("", [BEIJING], U_60_CENTS), ("", [BEIJING], U_60_CENTS), (FINAL, [], U_60_CENTS))
    events = collect(fake, budget=budget.Budget(limit_yuan=1.0))
    assert fake.count == 2                                          # 第 3 次电话没有打
    assert [e["type"] for e in events] == ["step", "observation", "step", "final"]
    assert events[-1]["text"] == "[预算用完] 已花 1.200000 元，超过上限 1.0 元 —— 这一轮之后不再打电话"
    assert events[-1]["step"] == 2


def test_loop_still_delivers_an_answer_that_is_already_paid_for():
    fake = CostedSend(("", [BEIJING], U_60_CENTS), (FINAL, [], U_60_CENTS))
    events = collect(fake, budget=budget.Budget(limit_yuan=1.0))
    assert events[-1] == {"type": "final", "step": 2, "text": FINAL}


def test_run_react_returns_the_bill_when_the_loop_stops():
    fake = CostedSend(("", [BEIJING], U_ONE_YUAN), ("", [BEIJING], U_ONE_YUAN), (FINAL, [], U_ONE_YUAN))
    answer = asyncio.run(fc_loop.run_react(QUESTION, TOOLS, send=fake, budget=budget.Budget(limit_yuan=1.0)))
    assert answer.startswith("[预算用完] 已花 2.000000 元，超过上限 1.0 元")
