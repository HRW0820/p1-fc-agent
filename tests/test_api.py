"""W2-S1 测试规格：FastAPI 最小服务（/health + /echo）

TDD 流程：先跑本文件 → 9 个测试全红（p1_fc_agent.app 模块不存在）
→ 实现 src/p1_fc_agent/app.py → 全绿（29 旧 + 9 新 = 38）

契约摘要（实现前先读完，想清楚再动手）：
- GET /health → 200 {"status": "ok"}
- POST /echo 收 EchoRequest 模型：
    message: str   —— min_length=1，且不能是纯空白（自定义校验，错误消息含"空白"）
    repeat:  int   —— default=1，范围 1 ≤ repeat ≤ 5
    模型整体：extra="forbid"（多余字段拒绝，不是忽略）
  正常 → 200 {"message": ..., "repeat": ...}
  坏参数 → 422，detail[0] 就是 S3 学的 Pydantic 错误结构（type/loc/msg/input）
"""

from fastapi.testclient import TestClient

from p1_fc_agent.app import app

client = TestClient(app)


# ---------- /health ----------

def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------- /echo 正常路径 ----------

def test_echo_ok():
    r = client.post("/echo", json={"message": "你好", "repeat": 3})
    assert r.status_code == 200
    assert r.json() == {"message": "你好", "repeat": 3}


def test_echo_repeat_default():
    """不给 repeat 时用默认值 1"""
    r = client.post("/echo", json={"message": "hi"})
    assert r.status_code == 200
    assert r.json()["repeat"] == 1


def test_echo_str_repeat_coerced():
    """P003 呼应：str→int 在 Pydantic v2 lax 模式下会智能转换（'3' → 3）
    （对比：int→str 不会转——S3 实测过的 city=123 被拒）"""
    r = client.post("/echo", json={"message": "hi", "repeat": "3"})
    assert r.status_code == 200
    assert r.json()["repeat"] == 3


# ---------- /echo 拒绝路径：422 + Pydantic 错误结构 ----------

def test_echo_missing_message():
    r = client.post("/echo", json={})
    assert r.status_code == 422
    err = r.json()["detail"][0]
    assert err["type"] == "missing"
    assert err["loc"] == ["body", "message"]


def test_echo_repeat_out_of_range():
    r = client.post("/echo", json={"message": "hi", "repeat": 99})
    assert r.status_code == 422
    assert r.json()["detail"][0]["type"] == "less_than_equal"


def test_echo_blank_message():
    r = client.post("/echo", json={"message": "   "})
    assert r.status_code == 422
    assert "空白" in r.json()["detail"][0]["msg"]


def test_echo_extra_field_forbidden():
    """模型幻觉一个不存在的字段 → 必须拒绝（Web 默认是忽略，我们主动收紧）"""
    r = client.post("/echo", json={"message": "hi", "hobby": "钓鱼"})
    assert r.status_code == 422
    err = r.json()["detail"][0]
    assert err["type"] == "extra_forbidden"
    assert err["loc"] == ["body", "hobby"]


def test_echo_repeat_not_numeric():
    r = client.post("/echo", json={"message": "hi", "repeat": "很多"})
    assert r.status_code == 422
    assert r.json()["detail"][0]["type"] == "int_parsing"
