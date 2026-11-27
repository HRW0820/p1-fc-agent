r"""W3 预备课（Session 0）测试规格：接真模型之前，先给 /ask 清账

TDD 流程：先跑本文件 → 5 failed, 2 passed
→ 按讲义第六节的四步走实现 → 全绿（81 旧 + 7 新 = 88）

为什么有这一课：W3 要把假大脑换成真模型，每次调用都要花钱、都可能断线。
W2 的 /ask 是按"假大脑永远不出错"写的，留下三笔账：
  ① 没有鉴权：/calculator 要查卡，/ask 不要。接上真模型，等于把钱包放在门口
  ② 流到一半出错，客人只看到连接断开，没有一句话（W2-S3 观察点 2 量过）
  ③ P012（大脑里写 time.sleep）当时 73 条测试全绿，没有一条抓得住

今天只改 src/p1_fc_agent/app.py 和 README.md，再给 tests/test_ask.py 补请求头。
react_loop.py 不动（只补一个文件末尾的换行）；讲义 1 的 llm.py 也只补换行。

A. 上锁：没有 key 的人，连流都开不了（3 条）
  /ask 和 /calculator 一样，参数里声明 Depends(require_api_key)（W2-S2 的查卡函数，照抄）
    - 没带 key、key 错 → 401，detail 含 "API Key"，响应是 JSON 不是流
    - 没带 key 且问题是空白 → 401 不是 422：先查卡后验单（W2-S2 观察点 1）

B. 流到一半出错：客人要听到一句话（3 条）
  ask_stream 里，循环中途抛了 Exception：
    - 已经推出去的事件不收回，然后补一条 {"type": "error", "message": ...}，最后照旧有 done
    - error 的 message 是一句固定的话，不许带异常原文（W2-S2：500 不把堆栈泄给调用方）
    - 异常原文要进服务端日志（用 logging.exception，讲义里教）
    - 客户端中途走了是 asyncio.CancelledError，它不是 Exception 的子类：
      不许把它包装成 error 事件，必须原样传回去（W2-S3 观察点 3）
      这一条现在就是绿的，它是守卫：防止有人把 except Exception 写成 except BaseException

C. 并发回归（1 条）：P012 说"要加一条多位客人同时问、总耗时不翻倍的测试"，就是它
  5 位客人同时消费 ask_stream：总耗时和 1 位差不多（约 0.36 秒），断言小于 0.7 秒
  这一条现在也是绿的。把 mock_llm 里的 await asyncio.sleep 改成 time.sleep，它会红（讲义观察点 3）

curl 对照（真人模式在讲义第六节第 3 步）：
  curl -i -N -X POST http://127.0.0.1:8000/ask -H "X-API-Key: dev-key" -H "Content-Type: application/json" -d '{"question":"北京和上海今天的气温相差多少度？"}'
"""

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from p1_fc_agent.app import app, ask_stream
from p1_fc_agent.react_loop import mock_llm

QUESTION = "北京和上海今天的气温相差多少度？"
TEST_KEY = "test-key"
GOOD_HEADERS = {"X-API-Key": TEST_KEY}
BAD_HEADERS = {"X-API-Key": "wrong-key"}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def fixed_api_key(monkeypatch):
    """测试环境把 key 固定成 TEST_KEY，不依赖"没设环境变量就用 dev-key"这个默认值"""
    monkeypatch.setenv("P1_API_KEY", TEST_KEY)


def parse_events(text: str) -> list[dict]:
    """把 SSE 响应体切成一条条事件（和 tests/test_ask.py 里的是同一个）"""
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


async def broken_brain(scratchpad: str) -> str:
    """第 2 次开口时断线。异常原文里故意放了不能给客人看的东西"""
    if scratchpad.count("Observation:") >= 1:
        raise RuntimeError("内部细节：模型接口返回 502，密钥是 sk-不能给客人看")
    return await mock_llm(scratchpad)


# ---------- A. 上锁 ----------

def test_ask_requires_key(client):
    """没带 key：401。响应是 JSON，不是流"""
    r = client.post("/ask", json={"question": QUESTION})
    assert r.status_code == 401
    assert "API Key" in r.json()["detail"]
    assert "text/event-stream" not in r.headers["content-type"]


def test_ask_rejects_wrong_key(client):
    r = client.post("/ask", json={"question": QUESTION}, headers=BAD_HEADERS)
    assert r.status_code == 401


def test_ask_key_checked_before_body(client):
    """没带 key，问题还是空白的：401 而不是 422（W2-S2 观察点 1 的老规矩）"""
    r = client.post("/ask", json={"question": "   "})
    assert r.status_code == 401


# ---------- B. 流到一半出错 ----------

def test_ask_stream_emits_error_then_done():
    """第 2 步大脑断线：前两条不收回，补一条 error，最后照旧有 done 收尾"""
    events = parse_events("".join(drain(ask_stream(QUESTION, brain=broken_brain))))
    assert [e["type"] for e in events] == ["step", "observation", "error", "done"]
    assert events[1]["text"] == "12"


def test_error_event_hides_details():
    """客人听到的是一句固定的话，异常原文一个字都不能漏到流里"""
    events = parse_events("".join(drain(ask_stream(QUESTION, brain=broken_brain))))
    error = events[-2]
    assert set(error) == {"type", "message"}
    assert "502" not in error["message"]
    assert "sk-" not in error["message"]


def test_cancel_is_not_converted_to_error():
    """客户端中途走了（CancelledError）：不许包装成 error 事件，必须原样传回去。
    把 except Exception 写成 except BaseException，这一条会红"""
    async def cancelled_brain(scratchpad: str) -> str:
        if scratchpad:
            raise asyncio.CancelledError
        return await mock_llm(scratchpad)

    with pytest.raises(asyncio.CancelledError):
        drain(ask_stream(QUESTION, brain=cancelled_brain))


# ---------- C. 并发回归（P012） ----------

def test_five_guests_do_not_queue():
    """5 位客人同时问：总耗时和 1 位差不多（约 0.36 秒）。
    谁在大脑里写了同步的 time.sleep（P012），5 × 4 × 0.05 秒的等待就变成排队，1 秒以上"""
    async def five():
        async def one():
            async for _ in ask_stream(QUESTION):
                pass

        t0 = time.perf_counter()
        await asyncio.gather(*(one() for _ in range(5)))
        return time.perf_counter() - t0

    assert asyncio.run(five()) < 0.7
