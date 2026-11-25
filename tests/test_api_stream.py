"""W2-S3 测试规格：SSE 流式接口（StreamingResponse + async generator）

TDD 流程：先跑本文件 → 9 个测试全红（sse 模块还不存在）
→ 按讲义第五节的 4 个步骤实现 → 全绿（46 旧 + 9 新 = 55）

本节做两样东西（/health /echo /tools /calculator 都不要动）：

A. 新文件 src/p1_fc_agent/sse.py
   - sse(data: dict) -> str：把一个 dict 变成**一条**标准 SSE 事件
     格式固定为 'data: ' + JSON + 两个换行符，中文保持原样（不能变成 \\u4f60）
   - async def token_stream(text: str, delay: float = 0.05)：async generator
     逐字推送：每个字符一条 {"type": "token", "index": 序号, "content": "字符"}
     最后一条 {"type": "done", "count": 字符数}
     每条之间 await asyncio.sleep(delay)（delay 为 0 时不睡）

B. app.py 新路由 POST /stream
   - 请求体 StreamRequest：
       text:  str，必填，不能是空白（min_length=1 + 自定义校验器）
       delay: float，默认 0.05，范围 0 到 1
       禁止多余字段
   - 响应：media_type 是 "text/event-stream"，响应头 Cache-Control: no-cache
   - 内容 = token_stream(text, delay) 的产出，一条不少、顺序不乱
   - text 空白 → 422（走你 S2 写的可读 message 处理器）

curl 对照（真人模式在讲义第五节第 4 步）：
  curl -N -X POST http://127.0.0.1:8000/stream -H "Content-Type: application/json" -d '{"text":"你好"}'
"""

import json
import time

import pytest
from fastapi.testclient import TestClient

from p1_fc_agent.app import app
from p1_fc_agent.sse import sse


def parse_events(text: str) -> list[dict]:
    """把 SSE 响应体切成一条条事件。标准 SSE：事件之间用一个空行隔开。"""
    return [json.loads(line[len("data: "):])
            for line in text.split("\n\n") if line.startswith("data: ")]


@pytest.fixture
def client():
    return TestClient(app)


# ---------- A. sse.py ----------

def test_sse_formatter_basic():
    assert sse({"a": 1}) == 'data: {"a": 1}\n\n'


def test_sse_formatter_keeps_chinese():
    """ensure_ascii 必须是 False，否则中文会变成 \\uXXXX 转义"""
    assert sse({"content": "你好"}) == 'data: {"content": "你好"}\n\n'


# ---------- B. /stream ----------

def test_stream_content_type(client):
    r = client.post("/stream", json={"text": "你好"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")


def test_stream_rejects_blank(client):
    r = client.post("/stream", json={"text": "   "})
    assert r.status_code == 422
    assert "message" in r.json()            # 走 S2 的可读 message 处理器


def test_stream_one_event_per_char_then_done(client):
    r = client.post("/stream", json={"text": "你好世界", "delay": 0})
    events = parse_events(r.text)
    assert [e["type"] for e in events] == ["token", "token", "token", "token", "done"]
    assert [e["content"] for e in events[:4]] == ["你", "好", "世", "界"]


def test_stream_index_increments_from_zero(client):
    events = parse_events(client.post("/stream", json={"text": "abcd", "delay": 0}).text)
    assert [e["index"] for e in events[:4]] == [0, 1, 2, 3]


def test_stream_ends_with_done_and_count(client):
    events = parse_events(client.post("/stream", json={"text": "三个字", "delay": 0}).text)
    assert events[-1] == {"type": "done", "count": 3}


def test_stream_is_progressive(client):
    """流式的灵魂：事件要一条条到，不能攒成一坨。
    4 个字、间隔 0.05s：token 在 0.05/0.10/0.15/0.20s 到，done 紧跟着最后一个
    所以第一个和最后一个之间至少隔 0.15s（留余量断言 0.12s）。攒一坨到的话间隔约等于 0"""
    stamps = []
    t0 = time.perf_counter()
    with client.stream("POST", "/stream", json={"text": "流式输出", "delay": 0.05}) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                stamps.append(time.perf_counter() - t0)
    assert len(stamps) == 5
    assert stamps[-1] - stamps[0] >= 0.12


def test_stream_no_cache_header(client):
    r = client.post("/stream", json={"text": "你好"})
    assert r.headers["cache-control"] == "no-cache"
