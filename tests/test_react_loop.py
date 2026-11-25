r"""W2-S4 测试规格：把 01_minimal_loop.py 的同步 ReAct 循环改成异步版

TDD 流程：先跑本文件 → 1 error（react_loop 模块还不存在）
→ 按讲义第六节的四步走实现 → 全绿（55 旧 + 9 新 = 64）

完成标志（计划原文）：async 版输出和同步版轨迹一致。
同步版就是 03-ReAct课程/01_minimal_loop.py，它不在仓库里，所以把它的真实输出抄在下面
当"标准答案"（GOLDEN）。异步版记下的 events 必须和它逐条相等。

新文件 src/p1_fc_agent/react_loop.py 要提供的东西：
  MAX_STEPS = 8
  @dataclass class RunResult：两个字段 answer: str、events: list[dict]
  事件（events 里的每一项）是字典，三种：
    {"type": "step",        "step": 第几步, "text": 大脑这一步的完整输出}
    {"type": "observation", "step": 第几步, "text": 工具结果或错误文本}
    {"type": "final",       "step": 第几步, "text": 最终答案}

  async def get_weather(city) -> str        先 await asyncio.sleep(0.05) 模拟网络，再查假数据
  async def calculator(expression) -> str   先 await asyncio.sleep(0.05)，再调 W1 的 run_calculator
  TOOLS = {"get_weather": (get_weather, 描述), "calculator": (calculator, 描述)}   形状和 01 相同
  async def mock_llm(scratchpad) -> str     先 await asyncio.sleep(0.05)，再按 01 的剧本回答
  async def run_react(question, *, brain=mock_llm, tools=TOOLS, max_steps=MAX_STEPS) -> RunResult

循环本体和 01 相同，只加两处 await：response = await brain(scratchpad)、observation = await func(arg)。
三条保护分支不许丢：工具不存在 → "错误：不存在工具 …" 当 Observation 喂回；
格式错误 → "格式错误：…" 当 Observation 喂回；超过 max_steps → 返回 "[强制终止] …"。

brain 和 tools 是参数（S2 依赖注入的思路搬到函数上）：循环不写死用哪个大脑、有哪些工具，
测试才能换剧本，W3 换 DeepSeek 时也只换 brain。
"""

import asyncio
import time

from p1_fc_agent.react_loop import (
    MAX_STEPS,
    TOOLS,
    RunResult,
    calculator,
    get_weather,
    mock_llm,
    run_react,
)

QUESTION = "北京和上海今天的气温相差多少度？"

# 01_minimal_loop.py 跑这个问题的真实输出，从 print 改写成事件
GOLDEN = [
    {"type": "step", "step": 1, "text": "Thought: 我需要先查北京的气温\nAction: get_weather[北京]"},
    {"type": "observation", "step": 1, "text": "12"},
    {"type": "step", "step": 2, "text": "Thought: 拿到北京 12 度，还需要上海的气温\nAction: get_weather[上海]"},
    {"type": "observation", "step": 2, "text": "20"},
    {"type": "step", "step": 3, "text": "Thought: 两个温度都有了，计算它们的差\nAction: calculator[20-12]"},
    {"type": "observation", "step": 3, "text": "8"},
    {"type": "step", "step": 4, "text": "Thought: 计算完成，我可以回答了\nFinal Answer: 北京和上海今天的气温相差 8 度。"},
    {"type": "final", "step": 4, "text": "北京和上海今天的气温相差 8 度。"},
]


def run(question=QUESTION, **kwargs):
    return asyncio.run(run_react(question, **kwargs))


# ---------- 完成标志：和 01 的轨迹一致 ----------

def test_trace_matches_sync_version():
    assert run().events == GOLDEN


def test_final_answer():
    assert run().answer == "北京和上海今天的气温相差 8 度。"


# ---------- 真的异步，不是只换了关键字 ----------

def test_tools_brain_and_loop_are_coroutine_functions():
    assert asyncio.iscoroutinefunction(run_react)
    assert asyncio.iscoroutinefunction(mock_llm)
    for func, _ in TOOLS.values():
        assert asyncio.iscoroutinefunction(func)


def test_default_run_takes_expected_time():
    """默认大脑和工具各睡 0.05 秒：4 次大脑 + 3 次工具 = 0.35 秒。
    任何一处内部漏了 await asyncio.sleep，轨迹一字不差，但耗时会变短。"""
    t0 = time.perf_counter()
    run()
    assert time.perf_counter() - t0 >= 0.3


def test_two_questions_run_concurrently():
    """两个问题同时问：应该和问一个差不多久（各睡各的），而不是翻倍。"""

    async def two():
        await asyncio.gather(run_react(QUESTION), run_react(QUESTION))

    t0 = time.perf_counter()
    asyncio.run(two())
    elapsed = time.perf_counter() - t0
    assert 0.3 <= elapsed < 0.6


# ---------- 三条保护分支（01 的老设计，异步版不许弄丢） ----------

def test_unknown_tool_is_fed_back():
    seen = []

    async def brain(scratchpad):
        seen.append(scratchpad)
        if len(seen) == 1:
            return "Thought: 试试不存在的工具\nAction: nope[北京]"
        return "Thought: 我改用别的办法\nFinal Answer: 已自纠错"

    result = run(brain=brain)
    assert result.answer == "已自纠错"
    assert "错误：不存在工具 nope" in result.events[1]["text"]
    assert "错误：不存在工具 nope" in seen[1]      # 错误被拼回上下文，大脑第二次能看到


def test_bad_format_is_fed_back():
    calls = []

    async def brain(scratchpad):
        calls.append(scratchpad)
        if len(calls) == 1:
            return "我不按格式说话"
        return "Final Answer: 已恢复"

    result = run(brain=brain)
    assert result.answer == "已恢复"
    observations = [e for e in result.events if e["type"] == "observation"]
    assert len(observations) == 1
    assert observations[0]["text"].startswith("格式错误")
    assert "格式错误" in calls[1]                # 错误被拼回上下文，大脑第二次能看到
    assert len(calls) == 2


def test_max_steps_fuse():
    async def brain(scratchpad):
        return "Thought: 我要一直查\nAction: get_weather[北京]"

    result = run(brain=brain, max_steps=3)
    assert result.answer.startswith("[强制终止]")
    assert len([e for e in result.events if e["type"] == "step"]) == 3
    assert MAX_STEPS == 8


# ---------- 返回类型 ----------

def test_returns_run_result():
    async def brain(scratchpad):
        return "Final Answer: 一步到位"

    result = run(brain=brain)
    assert isinstance(result, RunResult)
    assert isinstance(result.events, list)
    assert result.events == [
        {"type": "step", "step": 1, "text": "Final Answer: 一步到位"},
        {"type": "final", "step": 1, "text": "一步到位"},
    ]
