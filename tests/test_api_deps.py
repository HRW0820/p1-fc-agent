"""W2-S2 测试规格：依赖注入 + HTTPException + 全局异常处理器

TDD 流程：先跑本文件 → 8 个测试全红（路由都不存在，404）
→ 按讲义第五节的 5 个步骤实现 → 全绿（38 旧 + 8 新 = 46）

本节在 app.py 里新增三样东西（都在已有代码后面追加，不要动 /health 和 /echo）：

A. 工具菜单   GET  /tools/{tool_name}
     - 存在的工具 → 200 {"name", "description", "parameters"}
       （parameters 用 W1 模型的 model_json_schema() 自动生成）
     - 不存在 → 404，detail 里要包含"这个名字"和"可用工具名单"（至少含 calculator）
     - 工具名单至少三个：weather / population / calculator（模型都在 tools.py 里）

B. 会员制计算器  POST /calculator   请求体直接复用 W1 的 CalcQuery
     - 必须带请求头 X-API-Key，正确的 key 才能调用
     - key 从环境变量 P1_API_KEY 读（没设则用默认值 "dev-key"）
     - 没带 key 或 key 错 → 401，detail 含 "API Key"
     - 正常 → 200 {"result": <run_calculator 的返回值>}
     - 表达式运行出错（如 1/0）→ 仍是 200，result 里是错误文本（错误是数据，不是炸弹）

C. 全局异常处理器（统一出错话术）
     - 请求体校验失败：仍是 422，detail 照旧，**多一个 message 字段**——一句人类可读的摘要
       （用 W1-S3 的 format_validation_error 生成）
     - 其他未捕获异常：500，响应体 {"detail": "服务器内部错误"}（不把堆栈泄给调用方）

关于 fixture：文件里有个自动生效的 fixture，把 P1_API_KEY 固定成 "test-key"，
所以测试里正确的 key 就是 TEST_KEY——这是测试环境的规矩，实现时照常读环境变量即可。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from p1_fc_agent.app import app

TEST_KEY = "test-key"
GOOD_HEADERS = {"X-API-Key": TEST_KEY}


@pytest.fixture(autouse=True)
def fixed_api_key(monkeypatch):
    """autouse=True：每个测试运行前自动执行，把服务读到的 key 钉死。"""
    monkeypatch.setenv("P1_API_KEY", TEST_KEY)


@pytest.fixture
def client():
    return TestClient(app)


# ---------- A. 工具菜单 ----------

def test_tool_catalog_known(client):
    r = client.get("/tools/weather")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "weather"
    assert "city" in body["parameters"]["properties"]


def test_tool_catalog_unknown_404(client):
    r = client.get("/tools/nope")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert "nope" in detail          # 告诉调用方它问的是哪个
    assert "calculator" in detail    # 顺便告诉它有哪些可以问


# ---------- B. 会员制计算器 ----------

def test_calculator_requires_key(client):
    r = client.post("/calculator", json={"expression": "1+1"})     # 没带 key
    assert r.status_code == 401


def test_calculator_rejects_wrong_key(client):
    r = client.post("/calculator", json={"expression": "1+1"},
                    headers={"X-API-Key": "wrong-key"})   # 注意：请求头的值只能是 ASCII
    assert r.status_code == 401
    assert "API Key" in r.json()["detail"]


def test_calculator_ok(client):
    r = client.post("/calculator", json={"expression": "1+2*3"}, headers=GOOD_HEADERS)
    assert r.status_code == 200
    assert r.json() == {"result": "7"}


def test_calculator_runtime_error_is_data(client):
    """1/0 过了字符集校验，但运行时炸——应该变成 200 + 错误文本，而不是 500"""
    r = client.post("/calculator", json={"expression": "1/0"}, headers=GOOD_HEADERS)
    assert r.status_code == 200
    assert "工具执行失败" in r.json()["result"]


# ---------- C. 全局异常处理器 ----------

def test_validation_error_has_readable_message(client):
    """"abc" 有非法字符 → CalcQuery 的字符集校验拒绝 → 422，且带可读摘要"""
    r = client.post("/calculator", json={"expression": "abc"}, headers=GOOD_HEADERS)
    assert r.status_code == 422
    body = r.json()
    assert body["detail"][0]["type"] == "value_error"      # 原有的结构化错误照旧
    assert "非法字符" in body["message"]                   # 新增：一句人话


def test_unhandled_exception_returns_json_500():
    """不往 app 里放假的崩溃路由——单独搭一个会炸的小 app，装上同一个处理器来测"""
    handler = app.exception_handlers.get(Exception)
    assert handler is not None, "还没有注册全局异常处理器"

    broken = FastAPI()
    broken.add_exception_handler(Exception, handler)

    @broken.get("/boom")
    async def boom():
        raise RuntimeError("数据库炸了")

    r = TestClient(broken, raise_server_exceptions=False).get("/boom")
    assert r.status_code == 500
    assert r.json() == {"detail": "服务器内部错误"}
