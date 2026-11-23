# 踩坑日志（面试弹药库）

> 格式：编号 · 日期 · 标题 ｜ 现象 → 根因 → 修复 → 一句话教训

## P001 · 2026-11-20 · uv init 模板与讲义不符

- **现象**：`test_smoke` 导入 `__app_version__` 报 ImportError
- **根因**：uv 0.13.9 生成的 `__init__.py` 只有 `main()`，无版本变量；讲义基于旧模板假设
- **修复**：手动添加 `__app_version__ = "0.1.0"`
- **教训**：报错先逐词读——错误信息里的路径证明"包已找到、src 布局导入机制正常"，问题只在校验的假设上；外部教程的默认模板假设要先用 `cat` 验证

## P002 · 2026-11-20 · commit message 与实际内容不符

- **现象**：提交信息写"修复冒烟测试 + 首条踩坑日志"，但 pitfalls.md 没建，未进提交
- **根因**：写提交信息时是"意图"而非"实际 diff"
- **修复**：本文件补录，随 Session 2 提交
- **教训**：`git commit -m` 之前先 `git status` 确认要提交的文件清单；面试官 review 仓库时，message 与内容不符是减分项

## P003 · 2026-11-20 · 教程知识过时：Pydantic v1 的宽松转换在 v2 不成立

- **现象**：讲义称 `city=123` 会被"强制转换"成 `"123"`，实际 v2.14 直接抛 `string_type` 错误
- **根因**：该行为是 Pydantic v1 的 lax 模式默认；v2 默认 smart 模式下 int→str **不**自动转换（int→float、str→int 才会）
- **修复**：区分"拒绝"与"智能转换"——v2 里 `str` 字段收 int = 拒绝；`float` 字段收 int、`list[int]` 收 str 列表 = 转换
- **教训**：版本敏感的知识（库的默认行为）必须用当前版本跑通验证再写进文档；"终端输出 > 教程说法 > 记忆"——AI 生成的内容同样要跑一遍才知道真假

## P004 · 2026-11-23 · 调用 async 函数忘了 await（coroutine never awaited）

- **现象**：`async_demo.py` 结尾 `lazy = fetch_weather("杭州", delay=0.1)` 只调用没 await，程序结束时抛 `RuntimeWarning: coroutine 'fetch_weather' was never awaited`
- **根因**：`async def` 函数调用**不执行**，只返回 coroutine"懒"对象——造了单但没下锅。懒是并发的地基（可以一次造三个再 gather 点火），但代价是"忘了点火"不报错、只警告
- **修复**：任何 coroutine 对象必须被 `await`（单个）或交给 `gather(*coros)`（一批）
- **教训**：S4 的串行测试设了耗时下限断言（≥0.85s）专门抓这个坑——忘 await 的函数会"瞬间跑完"，结果列表里全是懒对象。看到 RuntimeWarning = 有任务没执行，别忽略它

## P005 · 2026-11-23 · 脚本顶层裸写 await 直接 SyntaxError

- **现象**：在普通 `.py` 脚本顶层写 `await asyncio.gather(...)`，得到 `SyntaxError: 'await' outside function`
- **根因**：`await` 只能在协程函数体内出现；脚本顶层的普通代码不在任何事件循环里，无处让出控制权
- **修复**：包进 `async def main(): ...`，再用 `asyncio.run(main())` 从外部点火——`asyncio.run` 就是"异步世界"唯一的入口
- **教训**：异步代码是"两层世界"——外层同步世界靠 `asyncio.run` 进内层异步世界；一个程序通常只点火一次（pytest 每用例各调一次是特例）

## P006 · 2026-11-23 · 在源头吞掉本该上抛的异常（分层合同违反）

- **现象**：`test_timeout_raises` 失败（`pytest.raises(TimeoutError)` 没等到异常）；`fetch_with_timeout` 里写了 `except TimeoutError: return "超时"`，还有一处 `zip(labels, ...)` 引用未定义变量
- **根因**：没想清楚**分层合同**——wait_for 层的职责就是"抛出 TimeoutError 作为 retry 层的原料"，源头把它吃掉，retry 层瞬间无活可干，三层架构塌成一层；labels 则是想用了才发现没人定义
- **修复**：删掉 try/except 让异常自然上抛；`labels = [label for label, _ in calls]` 从入参拆出
- **附**：第二版错误串 `f"工具异常: {label}: {r}"` 缺 `{type(r).__name__}`——`str(异常)` 只有消息没有类型名，模型失去"改参数还是换工具"的纠错线索
- **教训**：分层设计先写清楚每层的输入/输出契约（**谁抛、谁捕、谁转**），异常处理放错层是韧性层最常见的真实错误；TDD 的合同测试就是抓这种违约的——4 个红测试精确定位了 3 个合同违反点

