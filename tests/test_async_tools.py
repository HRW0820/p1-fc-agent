"""W1 Session 4 · asyncio 基础的测试规格（TDD：先红后绿）

任务：新建 src/p1_fc_agent/async_tools.py，实现 fetch_weather / fetch_all_serial / fetch_all_parallel，
另热身修复 tools.py 里 run_calculator 的错误标签 bug。

本文件 6 个测试全绿 + 旧的 16 个保持全绿 = 目标 22 passed。
耗时断言的余量已放宽（本机实测：串行 0.9s / 并行 0.4s），慢机器也留了 0.2s 余地。
"""
import asyncio
import time

import pytest

from p1_fc_agent.async_tools import (
    fetch_all_parallel,
    fetch_all_serial,
    fetch_weather,
)
from p1_fc_agent.tools import run_calculator


# ---------- 0. 热身：修复 S3 遗留的标签 bug ----------

def test_run_calculator_execution_error_label():
    """'1/0' 参数完全合法（海关放行对），是执行时才炸——
    所以标签必须是'工具执行失败'（模型该换策略），不是'参数校验失败'（模型该改参数）。"""
    out = run_calculator("1/0")
    assert out.startswith("工具执行失败")
    assert not out.startswith("参数校验失败")
    # 顺带确认没把合法行为改坏：
    assert run_calculator("20 - 12") == "8"


# ---------- 1. 协程的"懒" ----------

def test_call_returns_lazy_coroutine():
    """调用 async 函数不执行，返回 coroutine 对象；asyncio.run 才真正点火。"""
    coro = fetch_weather("北京", delay=0.0)
    assert asyncio.iscoroutine(coro)          # 懒对象，什么都没发生
    assert asyncio.run(coro) == "北京: 晴 25 度"   # 点火后才有结果


# ---------- 2. 串行 = 各段之和 ----------

def test_serial_takes_sum_of_delays():
    """3 个城市 delays=[0.4,0.3,0.2]，串行总耗时 >= 0.85s（实测 ~0.9s）。

    如果你忘了写 await：函数瞬间跑完、列表里全是 coroutine 对象——
    这个耗时断言会当场抓住你（asyncio 新手第一大坑的自动检测）。"""
    cities = ["北京", "上海", "广州"]
    delays = [0.4, 0.3, 0.2]

    t0 = time.monotonic()
    result = asyncio.run(fetch_all_serial(cities, delays))
    elapsed = time.monotonic() - t0

    assert elapsed >= 0.85                 # 真的串行等待过
    assert len(result) == 3
    for city, r in zip(cities, result):
        assert r.startswith(city)          # 结果和城市对应


# ---------- 3. 并行 = 最慢的那个 ----------

def test_parallel_takes_max_of_delays():
    """同样 3 个任务，gather 并行耗时 < 0.6s（实测 ~0.4s）——显著快于串行的 0.9s。"""
    cities = ["北京", "上海", "广州"]
    delays = [0.4, 0.3, 0.2]

    t0 = time.monotonic()
    result = asyncio.run(fetch_all_parallel(cities, delays))
    elapsed = time.monotonic() - t0

    assert elapsed < 0.6                   # 不是 0.9s 的叠加！
    assert len(result) == 3


def test_parallel_result_matches_serial():
    """并发不改变结果内容：parallel 的输出和 serial 完全一致。"""
    cities = ["北京", "上海", "广州"]
    delays = [0.4, 0.3, 0.2]

    serial = asyncio.run(fetch_all_serial(cities, delays))
    parallel = asyncio.run(fetch_all_parallel(cities, delays))
    assert parallel == serial


# ---------- 4. gather 保序 ----------

def test_parallel_preserves_input_order():
    """慢城(0.4s)在前、快城(0.1s)在后——快城先完成也不插队，
    结果位置永远等于传入位置。Agent 里'第 i 个城市 = results[i]'直接可用。"""
    cities = ["慢城", "快城"]
    delays = [0.4, 0.1]

    result = asyncio.run(fetch_all_parallel(cities, delays))

    assert result[0].startswith("慢城")     # 位置没变，尽管快城早就跑完了
    assert result[1].startswith("快城")
