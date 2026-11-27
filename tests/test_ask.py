r"""W2 周末大产出 测试规格：/ask 接口（POST 问题 → SSE 流式返回每一步）

TDD 流程：先跑本文件 → 1 error（cannot import name 'react_events'）
→ 按讲义第六节的七步走实现 → 全绿（64 旧 + 9 新 = 73）

完成标志（计划原文）：/ask 接口：POST 问题 → 流式返回每一步 Thought/Action/Observation（SSE 事件流）。

今天做两样东西（已有的 /health /echo /tools /calculator /stream 都不要动）：

A. src/p1_fc_agent/react_loop.py：把循环改成"边跑边给"
  async def react_events(question, *, brain=mock_llm, tools=TOOLS, max_steps=MAX_STEPS)
    异步生成器（async def + yield）：每发生一件事就 yield 一条事件，事件格式和 W2-S4 完全相同。
    S4 是把事件 append 进列表、跑完再整箱返回；今天改成做完一件就递出去。
  run_react 不删：变成薄薄一层，用 async for 把 react_events 吐出的事件收进列表再打包。
    → S4 的 9 条测试一个字不改，必须还是绿的（换壳不许换货）。

B. app.py 新路由 POST /ask
  请求体 AskRequest：question 为 str，必填、不能空白、禁止多余字段（照 W2-S3 的 StreamRequest 写）
  async def ask_stream(question, *, brain=mock_llm)：异步生成器
    react_events 的每条事件用 W2-S3 的 sse() 包成一条 SSE，最后补一条 {"type": "done"}
  响应：media_type "text/event-stream"，响应头 Cache-Control: no-cache（照 /stream）
  question 空白 → 422，带 message（W2-S2 的可读处理器）

curl 对照（真人模式在讲义第六节第 5 步）：
  curl -N -X POST http://127.0.0.1:8000/ask -H "Content-Type: application/json" -d '{"question":"北京和上海今天的气温相差多少度？"}'
"""

import asyncio
import inspect
import json
import time

import pytest
from fastapi.testclient import TestClient

from p1_fc_agent.app import app
from p1_fc_agent.react_loop import react_events, run_react

QUESTION = "北京和上海今天的气温相差多少度？"

TEST_KEY = "test-key"
GOOD_HEADERS = {"X-API-Key": TEST_KEY}


@pytest.fixture(autouse=True)
def fixed_api_key(monkeypatch):
    monkeypatch.setenv("P1_API_KEY", TEST_KEY)

@pytest.fixture
def client():
    return TestClient(app)


def parse_events(text: str) -> list[dict]:
    """把 SSE 响应体切成一条条事件。标准 SSE：事件之间用一个空行隔开。"""
    return [json.loads(line[len("data: "):])
            for line in text.split("\n\n") if line.startswith("data: ")]


def drain(agen) -> list:
    """用 async for 把一个异步生成器吐出的东西一条条收成列表"""
    async def consume():
        items = []
        async for item in agen:
            items.append(item)
        return items
    return asyncio.run(consume())


def collect(question=QUESTION, **kwargs) -> list[dict]:
    return drain(react_events(question, **kwargs))


# ---------- A1. 循环改成了生成器 ----------

def test_react_events_is_async_generator():
    """react_events 是异步生成器（yield），run_react 还是协程函数（await）：两种函数各干各的"""
    assert inspect.isasyncgenfunction(react_events)
    assert asyncio.iscoroutinefunction(run_react)


def test_react_events_same_as_run_react():
    """换壳不许换货：从生成器一条条拿到的，和 run_react 整箱给的逐条相等"""
    assert collect() == asyncio.run(run_react(QUESTION)).events


# ---------- A2. 真的边跑边给，不是跑完再倒出来 ----------

def test_react_events_is_progressive():
    """大脑和工具各睡 0.05 秒：第 1 条在 0.05 秒就到，最后一条 0.35 秒才到。
    如果是跑完再一次性给，第 1 条也要等到 0.35 秒"""
    stamps = []

    async def consume():
        async for event in react_events(QUESTION):
            stamps.append(time.perf_counter())

    t0 = time.perf_counter()
    asyncio.run(consume())
    assert len(stamps) == 8
    assert stamps[0] - t0 < 0.25
    assert stamps[-1] - stamps[0] >= 0.25


def test_ask_stream_is_progressive(client):
    """流式的灵魂：事件要一条条到，不能攒成一坨。
    共 9 条，第 1 条 0.05 秒到，最后一条 0.35 秒到（留余量断言 0.25）"""
    stamps = []
    t0 = time.perf_counter()
    with client.stream("POST", "/ask", json={"question": QUESTION}, headers=GOOD_HEADERS) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                stamps.append(time.perf_counter() - t0)
    assert len(stamps) == 9
    assert stamps[0] < 0.25
    assert stamps[-1] - stamps[0] >= 0.25


# ---------- B. /ask 的协议 ----------

def test_ask_headers(client):
    r = client.post("/ask", json={"question": QUESTION}, headers=GOOD_HEADERS)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-cache"


def test_ask_event_sequence(client):
    events = parse_events(client.post("/ask", json={"question": QUESTION}, headers=GOOD_HEADERS).text)
    assert [e["type"] for e in events] == [
        "step", "observation", "step", "observation",
        "step", "observation", "step", "final", "done",
    ]
    assert events[-1] == {"type": "done"}


def test_ask_events_match_loop(client):
    """线上推的每一条，和循环内部记的逐条相等"""
    events = parse_events(client.post("/ask", json={"question": QUESTION}, headers=GOOD_HEADERS).text)
    assert events[:-1] == asyncio.run(run_react(QUESTION)).events
    assert events[-2]["text"] == "北京和上海今天的气温相差 8 度。"


def test_ask_rejects_bad_request(client):
    blank = client.post("/ask", json={"question": "   "}, headers=GOOD_HEADERS)
    assert blank.status_code == 422 and "message" in blank.json()
    extra = client.post("/ask", json={"question": QUESTION, "delay": 0}, headers=GOOD_HEADERS)
    assert extra.status_code == 422
    missing = client.post("/ask", json={}, headers=GOOD_HEADERS)
    assert missing.status_code == 422


def test_ask_fuse_still_ends_with_done():
    """保险丝烧了（大脑一直不收工）：流里没有 final，但必须有 done 收尾，否则前端不知道结束了"""
    from p1_fc_agent.app import ask_stream     # 第 4 步才出生，放函数里 import，免得整文件收集阶段就报 error

    async def never_stop(scratchpad):
        return "Thought: 我要一直查\nAction: get_weather[北京]"

    events = parse_events("".join(drain(ask_stream(QUESTION, brain=never_stop))))
    assert [e["type"] for e in events] == ["step", "observation"] * 8 + ["done"]
