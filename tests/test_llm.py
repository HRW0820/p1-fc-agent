"""W3-S1 规格：p1_fc_agent.llm —— 裸调真模型的最小封装（10 条，没有一条花过钱）。

要做什么：
1. load_api_key：从 .env 文件读 DEEPSEEK_API_KEY（环境变量里已经有，就用环境变量的）；读不到报一句人话
2. chat：把 messages 交给 send 发出去，返回 (回复文本, 用量)。send 默认是真的 post，测试换成假的
3. cost：按用量和单价算出这次调用花了多少元。输入分"缓存命中"和"缓存未命中"两档，输出一档

约束：
- 发出去的请求体固定五样：model、messages、max_tokens、temperature、thinking（关闭思考）
- chat 自己不发网络请求：全部交给 send；回复只从 data["choices"][0]["message"]["content"] 取
- 每一条测试都不碰网络，也不读仓库根目录的 .env：没有 key 的机器上也要全绿

先红后绿的步骤见讲义 W3-讲义-1 第六节。
"""

import asyncio
import os

import pytest

from p1_fc_agent import llm


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """把 os.environ 换成一份复印件：load_dotenv 改的是进程的环境变量，不隔离会串到下一条测试"""
    monkeypatch.setattr(os, "environ", os.environ.copy())
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)      # 你自己终端里导出的 key 也不许被读到


class FakeSend:
    """假的 send：不发网络请求，只记下请求体，返回事先准备好的数据"""

    def __init__(self, reply="二", finish="stop"):          # finish：这条假回复为什么停下
        self.payloads = []
        self.data = {
            "choices": [{"finish_reason": finish, "message": {"role": "assistant", "content": reply}}],
            "usage": {"prompt_tokens": 13, "completion_tokens": 1, "prompt_cache_hit_tokens": 0},
        }

    async def __call__(self, payload):
        self.payloads.append(payload)
        return self.data


def chat_with(fake, messages, **options):
    return asyncio.run(llm.chat(messages, send=fake, **options))


# ---------- 第 1 组：读 key（2 条） ----------

def test_load_api_key_reads_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=sk-from-file\n", encoding="utf-8")
    assert llm.load_api_key(str(env_file)) == "sk-from-file"


def test_load_api_key_missing_raises(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_KEY=sk-wrong-name\n", encoding="utf-8")   # 键名拼错了，等于没有
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        llm.load_api_key(str(env_file))


# ---------- 第 2 组：发出去的请求体（3 条） ----------

def test_chat_sends_expected_payload():
    fake = FakeSend()
    messages = [{"role": "user", "content": "用两个字回答：1+1等于几"}]
    chat_with(fake, messages)
    assert fake.payloads == [{
        "model": "deepseek-flash",
        "messages": messages,
        "max_tokens": 256,
        "temperature": 0.0,
        "thinking": {"type": "disabled"},
    }]


def test_chat_passes_options_through():
    fake = FakeSend()
    chat_with(fake, [{"role": "user", "content": "用一句话介绍长城"}], max_tokens=5, temperature=0.7)
    assert fake.payloads[0]["max_tokens"] == 5
    assert fake.payloads[0]["temperature"] == 0.7


def test_chat_returns_text_and_usage():
    fake = FakeSend(reply="长城是横亘中国")
    text, usage, finish_reason, _ = chat_with(fake, [{"role": "user", "content": "用一句话介绍长城"}])
    assert text == "长城是横亘中国"
    assert usage == {"prompt_tokens": 13, "completion_tokens": 1, "prompt_cache_hit_tokens": 0}
    assert finish_reason == "stop"                              # W3-S2 补：这一项以前在 chat 里丢了（P015）


# ---------- 第 3 组：算钱（3 条） ----------

def test_cost_of_a_small_call():
    usage = {"prompt_tokens": 13, "completion_tokens": 1, "prompt_cache_hit_tokens": 0}
    assert llm.cost(usage) == pytest.approx(0.000017)        # 13 × 1 元 + 1 × 4 元，每百万


def test_cost_counts_cache_hits_cheaper():
    usage = {"prompt_tokens": 679, "completion_tokens": 6, "prompt_cache_hit_tokens": 512}
    assert llm.cost(usage) == pytest.approx(0.00020124)      # 512 × 0.02 元 + 167 × 1 元 + 6 × 4 元


def test_cost_with_peak_price():
    usage = {"prompt_tokens": 13, "completion_tokens": 1, "prompt_cache_hit_tokens": 0}
    peak = {"hit": 0.04, "miss": 2.0, "out": 8.0}            # 高峰时段单价，空闲时段的两倍
    assert llm.cost(usage, peak) == pytest.approx(2 * 0.000017)


def test_chat_reports_finish_reason():
    fake = FakeSend(reply="", finish="length")                  # 话说到一半被掐断
    text, usage, finish_reason, _ = chat_with(fake, [{"role": "user", "content": "用一句话介绍长城"}])
    assert (text, finish_reason) == ("", "length")


def test_chat_passes_response_format():
    fake = FakeSend()
    chat_with(fake, [{"role": "user", "content": "上海天气怎么样"}], response_format={"type": "json_object"})
    assert fake.payloads[0]["response_format"] == {"type": "json_object"}
