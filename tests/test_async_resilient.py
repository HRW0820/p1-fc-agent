"""W1 Session 5 · asyncio 进阶的测试规格（TDD：先红后绿）

任务：新建 src/p1_fc_agent/resilient_tools.py，实现三件东西：
  1. fetch_with_timeout(city, delay, timeout)  —— wait_for 超时保险丝
  2. retry(make_call, timeout, max_attempts, label) —— 工厂重试（超时重试/其他穿透/耗尽返回错误字符串）
  3. gather_resilient(calls, timeout, max_attempts) —— retry + gather + return_exceptions 三层叠装

本文件 7 个测试 + 旧的 22 个保持全绿 = 目标 29 passed。

设计说明：
  - flaky/boom 都用"工厂 + 计数字典"构造（讲义第二节的前提 1：协程一次性，重试必须造新的）
  - 耗时断言依旧钉死关键语义：超时必须真的"掐死"任务（elapsed < 0.6 而不是 1.0+）
"""
import asyncio
import time

import pytest

from p1_fc_agent.resilient_tools import (
    fetch_with_timeout,
    gather_resilient,
    retry,
)


# ---------- 工具工厂：可控的假工具 ----------

def make_flaky_tool(fail_times: int):
    """前 fail_times 次慢到超时（sleep 1.0s），之后瞬间成功。
    返回 (make_call, calls)，calls["n"] 记录真实调用次数。"""
    calls = {"n": 0}

    async def tool():
        calls["n"] += 1
        if calls["n"] <= fail_times:
            await asyncio.sleep(1.0)      # 慢到任何 timeout 都拦它
        return f"ok(attempt={calls['n']})"

    return tool, calls


def make_boom_tool():
    """每次调用都抛 ValueError——确定性故障，重试无意义。"""
    calls = {"n": 0}

    async def tool():
        calls["n"] += 1
        raise ValueError("参数错误，重试也没用")

    return tool, calls


# ---------- 1. wait_for：超时保险丝 ----------

def test_timeout_raises_and_task_cancelled():
    """delay=1.0 / timeout=0.3：抛 TimeoutError，且耗时 < 0.6s。
    如果 wait_for 不取消任务（等它跑完才抛），耗时会是 1.0s+。"""
    t0 = time.monotonic()
    with pytest.raises(TimeoutError):
        asyncio.run(fetch_with_timeout("慢城", delay=1.0, timeout=0.3))
    elapsed = time.monotonic() - t0
    assert elapsed < 0.6, f"任务没被取消？耗时 {elapsed:.2f}s"


def test_fast_call_returns_normally():
    """timeout 只是上限不是延时：快任务正常返回。"""
    result = asyncio.run(fetch_with_timeout("快城", delay=0.1, timeout=1.0))
    assert result.startswith("快城")


# ---------- 2. retry：工厂重试 ----------

def test_retry_succeeds_after_transient_failure():
    """抖一次就恢复的工具：第1次超时，第2次成功。"""
    tool, calls = make_flaky_tool(fail_times=1)
    t0 = time.monotonic()
    result = asyncio.run(retry(tool, timeout=0.3, max_attempts=3, label="天气API"))
    elapsed = time.monotonic() - t0

    assert result == "ok(attempt=2)"
    assert calls["n"] == 2                     # 真的调了 2 次
    assert elapsed < 0.9                       # 一次超时(0.3) + 一次秒成，远快于串行两次 1.0s


def test_retry_exhausted_returns_error_string():
    """永久超时的工具：耗尽次数后返回错误字符串（永不 raise TimeoutError）。"""
    tool, calls = make_flaky_tool(fail_times=99)
    t0 = time.monotonic()
    result = asyncio.run(retry(tool, timeout=0.3, max_attempts=3, label="天气API"))
    elapsed = time.monotonic() - t0

    assert isinstance(result, str)
    assert result.startswith("工具超时")
    assert "3" in result                       # 把尝试次数带回去
    assert calls["n"] == 3
    assert 0.85 <= elapsed < 1.2               # 3 × 0.3s 叠加（重试的延迟账）


def test_retry_propagates_non_timeout_errors():
    """ValueError 是确定性故障：立即穿透，不消耗重试次数。"""
    tool, calls = make_boom_tool()
    with pytest.raises(ValueError):
        asyncio.run(retry(tool, timeout=0.3, max_attempts=3, label="坏参数工具"))
    assert calls["n"] == 1                     # 只调了 1 次——没有盲目重试


# ---------- 3. gather_resilient：批量三层叠装 ----------

def test_gather_resilient_mixed_outcomes():
    """1 成功 + 1 永久超时 + 1 成功：错误降级成字符串，位置即身份。"""
    ok1, _ = make_flaky_tool(fail_times=0)
    dead, _ = make_flaky_tool(fail_times=99)
    ok2, _ = make_flaky_tool(fail_times=0)

    t0 = time.monotonic()
    results = asyncio.run(gather_resilient(
        [("A", ok1), ("B", dead), ("C", ok2)],
        timeout=0.3, max_attempts=2,
    ))
    elapsed = time.monotonic() - t0

    assert results[0] == "ok(attempt=1)"       # 位置 0 = A
    assert results[1].startswith("工具超时")     # 位置 1 = B（两次超时后降级成文本）
    assert "2" in results[1]                   # retry 层先消化（尝试2次），batch 拿到的是字符串
    assert results[2] == "ok(attempt=1)"       # 位置 2 = C
    assert elapsed < 1.5                       # 并行 + 各自 retry，远快于串行


def test_gather_resilient_converts_exceptions():
    """穿透上来的 ValueError 被 batch 层收编成字符串——三层里每层各司其职。"""
    ok, _ = make_flaky_tool(fail_times=0)
    boom, _ = make_boom_tool()

    results = asyncio.run(gather_resilient(
        [("好工具", ok), ("坏参数", boom)],
        timeout=0.3, max_attempts=2,
    ))

    assert results[0] == "ok(attempt=1)"
    assert isinstance(results[1], str)         # 不是异常对象——已被降级
    assert results[1].startswith("工具异常")
    assert "ValueError" in results[1]          # 异常类型要出现在喂回文本里（模型才知道是什么错）
