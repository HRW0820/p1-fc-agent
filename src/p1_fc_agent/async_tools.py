import asyncio

async def fetch_weather(city: str, delay: float = 0.5) -> str:
    """模拟 IO 工具：睡 delay 秒后返回天气文本。"""
    await asyncio.sleep(delay)
    return f"{city}: 晴 25 度"

async def fetch_all_serial(cities: list[str], delays: list[float] | None = None) -> list[str]:
    """串行版：逐个 await。"""
    if delays is None:
        delays = [0.5] * len(cities)     # 没给延时就全用 0.5
    results = []
    for city, d in zip(cities, delays):  # zip 把城市和延时一一配对
        result = await fetch_weather(city, d)   # ← 关键：每次真的等它完成
        results.append(result)
    return results

async def fetch_all_parallel(cities: list[str], delays: list[float] | None = None) -> list[str]:
    """并行版：asyncio.gather。delays 为 None 时每个城市用默认 0.5。"""
    if delays is None:
        delays = [0.5] * len(cities)
    # TODO 1：造 coroutine 列表（此刻还一个都没执行，都是"懒"对象）：
    coros = [fetch_weather(city, d) for city, d in zip(cities, delays)]
    # TODO 2：用 asyncio.gather 点火。关键知识点：
    #   gather 接收的是"一个个参数"，不是列表——
    #   怎么把列表 coros 拆成一串参数传进去？
    #   （提示：一个星号。答案形如 await asyncio.gather(<这里填>））
    return await asyncio.gather(*coros)