"""W3-S2 规格：p1_fc_agent.structured —— 让模型按一张固定的表格回答（10 条，没有一条花过钱）。

要做什么：
1. ParseError：自己定的一种异常。模型的回答变不成表格时，报错信息是一句能照着做的话
2. parse(text, model)：把一段文字变成 model 的一张表。两种死法都要接住，换成 ParseError：
   死法一：根本不是 JSON（被 ```json 围栏包着、只有空格、说到一半被掐断）→ 报错里有"不是合法的 JSON"
   死法二：是合法 JSON，但表格没填对（城市是空白的、自己加了字段）→ 报错里有"表格没填对"
   原始报错要挂在 ParseError 后面（__cause__），调试时还看得到原话
3. ask_json(messages, model)：店规里写明"JSON"和字段名，打开 JSON 模式发出去；
   finish_reason 不是 "stop" 就不解析，直接报 ParseError（报错里有"没说完"）

约束：
- ask_json 自己不发请求：全部交给 send，测试换成假的
- 每一条测试都不碰网络，也不读仓库根目录的 .env

先红后绿的步骤见讲义 W3-讲义-2 第六节。
"""

import asyncio
import json

import pytest
from pydantic import ValidationError

from p1_fc_agent import structured
from p1_fc_agent.tools import WeatherQuery          # W1 写的表格：city 必填、unit 默认 celsius、不许有多余字段

FENCED = '```json\n{"city": "上海", "unit": "celsius"}\n```'      # 不开 JSON 模式时模型的常见回答
TRUNCATED = '{"city": "上海", "unit": "摄氏度",'                 # max_tokens 太小时的实测回答


class FakeSend:
    """假的 send：记下请求体，回事先准备好的回答"""

    def __init__(self, reply='{"city": "上海", "unit": "celsius"}', finish="stop"):
        self.payloads = []
        self.data = {"choices": [{"finish_reason": finish, "message": {"role": "assistant", "content": reply}}],
                     "usage": {"prompt_tokens": 30, "completion_tokens": 12, "prompt_cache_hit_tokens": 0}}

    async def __call__(self, payload):
        self.payloads.append(payload)
        return self.data


def ask(fake, **options):
    return asyncio.run(structured.ask_json([{"role": "user", "content": "上海天气怎么样"}], WeatherQuery, send=fake, **options))


# ---------- 第 1 组：死法一，根本不是 JSON（3 条） ----------

def test_parse_rejects_fenced_json():
    with pytest.raises(structured.ParseError, match="不是合法的 JSON") as caught:
        structured.parse(FENCED, WeatherQuery)
    assert isinstance(caught.value.__cause__, json.JSONDecodeError)        # 原始报错挂在后面


def test_parse_rejects_blank_reply():
    with pytest.raises(structured.ParseError, match="不是合法的 JSON"):
        structured.parse("  ", WeatherQuery)        # JSON 模式下模型答不上来时，content 可能只有空格


def test_parse_rejects_truncated_json():
    with pytest.raises(structured.ParseError, match="第 1 行"):
        structured.parse(TRUNCATED, WeatherQuery)


# ---------- 第 2 组：死法二，是 JSON 但表格没填对；以及正常情况（3 条） ----------

def test_parse_fills_the_form():
    form = structured.parse('{"city": " 上海 ", "unit": "celsius"}', WeatherQuery)
    assert form == WeatherQuery(city="上海")        # 过了安检机：W1 的校验器照样工作，空格被去掉


def test_parse_rejects_blank_city():
    with pytest.raises(structured.ParseError, match="城市名不能为空白") as caught:
        structured.parse('{"city": "", "unit": ""}', WeatherQuery)       # 问"你好"时模型的实测回答：字段都在，城市是空的
    assert isinstance(caught.value.__cause__, ValidationError)


def test_parse_rejects_extra_fields():
    with pytest.raises(structured.ParseError, match="表格没填对"):
        structured.parse('{"city": "上海", "unit": "摄氏度", "date": "明天"}', WeatherQuery)     # W1-S3 的 extra="forbid"


# ---------- 第 3 组：ask_json 发出去什么、回来什么（4 条） ----------

def test_ask_json_sends_json_mode_and_field_names():
    fake = FakeSend()
    ask(fake)
    payload = fake.payloads[0]
    assert payload["response_format"] == {"type": "json_object"}
    rule = payload["messages"][0]
    assert rule["role"] == "system" and "JSON" in rule["content"]       # 官方要求：提示里必须有 json 字样，否则 400
    assert "city" in rule["content"] and "unit" in rule["content"]      # 字段名来自表格，不手写
    assert payload["messages"][1] == {"role": "user", "content": "上海天气怎么样"}


def test_ask_json_returns_form_and_usage():
    form, usage = ask(FakeSend())
    assert form == WeatherQuery(city="上海")
    assert usage["completion_tokens"] == 12


def test_ask_json_truncated_reply_raises():
    with pytest.raises(structured.ParseError, match="没说完"):
        ask(FakeSend(reply=TRUNCATED, finish="length"))


def test_ask_json_blank_reply_raises():
    with pytest.raises(structured.ParseError, match="不是合法的 JSON"):
        ask(FakeSend(reply="  "))
