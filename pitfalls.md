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

## P007 · 2026-11-23 · 顶层直接调 gather：没有事件循环

- **现象**：实验脚本写 `asyncio.run(asyncio.gather(a, b))` → `RuntimeError: There is no current event loop in thread 'MainThread'`，且伴随 never awaited 警告
- **根因**：`gather()` **被调用的那一刻**就需要事件循环来调度任务（内部 ensure_future 要找当前循环），而 `asyncio.run` 的循环在它内部才诞生——外层调用时循环还不存在
- **修复**：把 gather 写进协程函数体内：`async def main(): return await asyncio.gather(...)`，再 `asyncio.run(main())`
- **教训**：与 P005（顶层 await SyntaxError）同源——**进入异步世界的门只有 asyncio.run，门内才能用异步设施**；`run(coro)` 收的是协程，不是"已调度的 gather 结果"

## P008 · 2026-11-24 · 字段校验器写在类外面（IndentationError）

- **现象**：`pytest` 收集阶段直接报 `app.py, line 20 @classmethod IndentationError: unexpected indent`
- **根因**：`@field_validator` 写在了 `/echo` 路由**之后、且顶格**。Python 里类的身体靠缩进划定——`class EchoRequest` 下面第一次出现顶格代码（路由装饰器）时，类就"关门"了；后面的校验器实际挂在模块顶层，不属于任何类，而第 20 行又突然缩进 4 格，Python 不知道它是谁的
- **修复**：①校验器整段搬进类体（与 `message`/`repeat` 字段对齐，同缩进一层）②路由挪到类完整定义之后 ③顺手补 `from pydantic import field_validator`（修完前两条会撞 NameError）
- **教训**：**报错行号是"发现现场"不是"肇事现场"**——第 20 行没错，错在第 19 行的归属；"依赖某个类的东西必须定义在类关门之前"是通用的顺序规则。另一个信号：ImportError/IndentationError 发生在**收集阶段**（整文件一个测试都没跑），看到 `ERROR collecting` 就知道是模块级语法/导入问题，不是断言问题

## P009 · 2026-11-24 · 从 FastAPI 内部模块导入自己写的函数（ImportError）

- **现象**：`pytest` 收集阶段报 `ImportError: cannot import name 'format_validation_error' from 'fastapi.utils'`
- **根因**：`format_validation_error` 是 W1-S3 自己写在 `p1_fc_agent/tools.py` 里的函数，不是 FastAPI 的。用 AI 工具补全时，它看到"validation error"就猜成了 FastAPI 内部模块（`fastapi.utils`）
- **修复**：删掉 `from fastapi.utils import format_validation_error`，改为 `from p1_fc_agent.tools import ..., format_validation_error`
- **教训**：①**两种导入错误要分清**——`ModuleNotFoundError` 是"房子都不在"（模块路径错），`ImportError: cannot import name` 是"房子在，人不在"（模块对，名字错），后者先查"这个名字到底住在哪" ②**AI 生成的 import 行要逐个核对来源**：自己项目里的名字从自己的包导入，看到 `xxx.utils` / `xxx._internal` 这种内部模块路径要先停一下（AI Coding 纪律：每行都能解释） ③报错发生在收集阶段，整文件一个测试都没跑（P008 同款信号）

## P010 · 2026-11-25 · 把带 `#` 说明行的命令整块粘进终端（zsh: command not found: #）

- **现象**：把讲义里五条 `curl` 连同 `# ① 响应头……` 这样的说明行一起复制进终端，每条说明行报一次 `zsh: command not found: #`，`curl` 本身照常执行、结果正确
- **根因**：`#` 开头是写给人看的注释。zsh 在交互模式下默认**不把 `#` 当注释**，而是当成一个名字叫 `#` 的命令去找，找不到就报错。整块粘贴时说明行和命令行一起被送进去，所以报错和正常输出交替出现
- **修复**：只复制 `curl` 那一行。讲义已改成一条命令一个代码块，说明文字写在代码块外
- **教训**：①**报错要看它有没有影响结果**：这次是无害噪音（三条 `command not found`，结果全对），和"报错导致命令没跑"是两回事，先看输出再决定要不要慌 ②**复制粘贴的最小单位是一条命令**，不是一段代码块 ③让 zsh 承认交互式 `#` 注释的开关是 `setopt interactivecomments`（写进 `~/.zshrc`），这个没有实测，优先还是养成只粘命令的习惯

