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
## P011 · 2026-11-26 · 接错头：`/ask` 里用 `await run_react` 整箱拿再 `yield`，内容全对但不是流式

- **现象**：`ask_stream` 写成先 `result = await run_react(question, brain=brain)`，再 `for event in result.events: yield sse(event)`。`curl` 响应头照常 200，9 条事件的内容、顺序和正确版逐字相同；`pytest tests/test_ask.py` 是 `1 failed, 8 passed`，红的只有 `test_ask_stream_is_progressive`，断言是 `assert 0.36 < 0.25`（第一条事件要等整圈跑完才到）
- **根因**：`await run_react(...)` 要等整圈跑完才往下走，第一次 `yield` 时 9 条已经全部做好。流式看的是**每条什么时候交出去**，和内容无关。把假大脑放慢到每步 1 秒，实测差别一眼可见：整箱版 9 条全在 4.18 秒同一时刻到；正确版是 1.03、1.08、2.08、2.13、3.13、3.18、4.19、4.19、4.19
- **修复**：`ask_stream` 接 `react_events` 这一头：`async for event in react_events(question, brain=brain): yield sse(event)`
- **教训**：①**"9 条事件全对"不等于"流式"**。内容、顺序、条数、协议、响应头的测试它全过，只有计时测试抓得住，所以流式接口必须留一条 ②写流式接口时先问自己"第一条什么时候到"，不是"最后拿到什么" ③真模型一步 5 秒时（实测模拟）：正确版客人第 5 秒看到第一条 Thought，整箱版对着空白等 20 秒后一起刷出来，等于不流式

## P012 · 2026-11-26 · 用 `time.sleep` 顶替 `await asyncio.sleep`：73 条测试全绿，5 位客人同时问耗时变成 3 倍

- **现象**：把 `mock_llm` 里的 `await asyncio.sleep(0.05)` 改成 `time.sleep(0.05)`（S1 观察点 3 的老坑换了个地方）。`uv run pytest` 是 **73 passed**，一条不红；`curl` 输出一字不差。但 5 位客人同时问 `/ask`：正确版 0.37 秒，`time.sleep` 版 1.12 秒；2 位客人 0.37 秒对 0.45 秒
- **根因**：`time.sleep` 是同步阻塞，等的时候不交还事件循环，别的客人的请求只能排队。工具的 3 次等待没改、仍然重叠，所以只有大脑的 4 次等待在排队：5 位 × 4 步 × 0.05 秒 = 1 秒。实测每位客人各自等了 0.68、0.86、0.96、1.07、1.12 秒（按客人编号排）
- **修复**：改回 `await asyncio.sleep(0.05)`
- **教训**：①**测试全绿不等于并发没问题**。S4 留的两条计时测试只盯"两个问题并发"，压力太小，量不出排队的开始。要抓这种回归，得加一条"多位客人同时问、总耗时不翻倍"的测试（待加） ②模拟真模型一步 2 秒：正确版 1、2、5 位客人都是约 8.2 秒；`time.sleep` 版是 8.19、16.09、40.22 秒，5 位客人差 5 倍 ③`await` 漏在哪个函数里，哪个函数的等待就变成全服务排队。S4 的两个观察点里是漏了 `await`（等待消失，耗时变短），这次是换成了同步的等（等待还在，但排队，耗时变长）；症状相反，根因相同：等待没有交还事件循环，也就是 S1 观察点 3 纯思考过、这次才量到的那个差别

## P013 · 2026-11-26 · `question` 一路传进去却没人用：问什么都答"温差"

- **现象**：`POST /ask` 问"上海今天天气怎么样？"，返回的 9 条事件和问"北京和上海今天的气温相差多少度？"逐字相同，第一步还是"我需要先查北京的气温"。73 条测试全绿
- **根因**：`react_events(question, ...)` 的函数体里，`question` 只出现在定义行那一次。大脑每一步只收到草稿纸 `scratchpad`，第一张是空字符串 `''`。间谍大脑实测：4 张草稿纸里没有一处出现问题，`"上海今天天气怎么样" in "".join(seen)` 是 `False`。假大脑靠数草稿纸里有几个 `Observation:` 照剧本演，从来没读过问题
- **修复**：今天不修，假大脑用不上问题。W3 换真模型的第一步补**提示词模板**：把问题、有哪些工具能用、输出格式要求、之前的草稿纸拼在一起交给大脑
- **教训**：①一个参数从入口一路传到底却没被用上，Python 不报错，测试也不报错 ②测试只问了一个问题，所以发现不了"答案和问题无关"。要有一条"换问题、答案跟着变"的用例，等 W3 真大脑能读到问题后补 ③接口"能跑通、内容对"和"真的在处理输入"是两回事，验收时要故意换一个不相干的输入试试

## P014 · 2026-11-26 · OpenAI SDK 漏写 `base_url`：DeepSeek 的 key 被发到了 OpenAI 的服务器

- **现象**：接 DeepSeek 时写 `AsyncOpenAI(api_key=...)`，漏了 `base_url`。请求没有发到 DeepSeek，回的是 `openai.AuthenticationError: Error code: 401 - Incorrect API key provided…`。这一条是助手备课时在实验脚本里犯的，**用的是真 key**，当天已告知
- **根因**：OpenAI SDK 出厂默认连 OpenAI 自己的服务器。`api_key` 只是一个字符串，SDK 不知道它属于谁，照样放进 `Authorization` 头发出去。key 发给谁由 `base_url` 决定，和 key 本身无关
- **修复**：`post` 里写明 `AsyncOpenAI(base_url=BASE_URL, api_key=load_api_key())`。实验一律用假 key，或在不含 `.env` 的副本里做
- **教训**：①用第三方兼容接口，第一件事是核对地址，和核对 key 一样要紧 ②**别用真 key 做"写错的现场"实验**，写错的那个地方可能正好是"发给谁" ③同源的一条（实测）：在副本里删掉规格的 `isolated_env` 夹具、终端里又导出了真 key 时，pytest 的断言对比把真 key 打到了屏幕上。真 key 只该出现在 `.env` 里，测试永远读不到它，就不会被任何输出带出来
- **后续**：是否更换 key 由用户决定；换的话只改 `.env` 那一行

## P015 · 2026-11-26 · `chat` 只回 `content`，丢了 `finish_reason`：回复被掐断甚至为空，调用方无从知道

- **现象**：把 `chat` 里的思考打开（`"thinking": {"type": "enabled"}`），`max_tokens` 还是默认的 256。实测 6 遍里 4 遍输出正好 256 个 token，`finish_reason` 是 `length`，其中 1 遍 `content` 是空字符串 `''`，3 遍话说一半停住。而 `chat` 返回的是 `('', 用量)`，和一次正常回答长得一样。8 条测试全绿
- **根因**：`chat` 只取 `choices[0].message.content` 和 `usage`。`max_tokens` 是思考和回答**共用**的额度，思考长了回答就是空的；关闭思考时它也会发生：`max_tokens` 设 5 时回执是 `"content":"长城是中国古代为抵御"`、`"finish_reason":"length"`。规格里的 `FakeSend` 回的 `finish_reason` 永远是 `"stop"`，所以测试看不见这件事
- **修复**：没修。W3 解析模型输出那一课要把 `finish_reason` 一起带出来：是 `"length"` 就重试或报错，不能把半句话、空字符串当答案。（2026-11-27 W3-S2 已还：`chat` 带出 `finish_reason`，`ask_json` 在解析之前先检查它，`test_chat_reports_finish_reason` 和 `test_ask_json_truncated_reply_raises` 守着）
- **教训**：①**模型回了非空的字符串，不等于说完了**。生产里的 Agent 必须看 `finish_reason`，不能只看 `content` 非空 ②被掐断的半句话进了 ReAct 循环有两条路：没有 `Action:` 就走"格式错误"分支，在草稿纸里越滚越乱；掐在 `Final Answer:` 后面就更坏，循环当场收工，把半句话当答案交给客人 ③和 P011–P013 是同一家族：测试全绿，东西却不对。假的 `send` 测不到 `post`，也测不到真模型会话说到一半

## P016 · 2026-11-27 · 日志那一行没写、写错位置，88 条测试照样全绿

- **现象**：给 `/ask` 加完出错保护以后，在副本里一次只改一处（实测）：①删掉 `logger.exception("/ask 的流中断了")` 那一行 ②删掉顶部的 `logging.basicConfig(...)` ③把 `logger.exception(...)` 挪进 `try`、放在 `for` 循环后面。三种写法新规格都是 `7 passed`、全量都是 `88 passed`。真起服务让工具断一次线：①服务端终端只有访问日志，出错经过一点没留；②traceback 还在，但第一行是光秃秃的 `/ask 的流中断了`，没有 `ERROR:p1_fc_agent.app:`；③正好反了，出错时什么都不记，正常问答完倒记一条 `ERROR:p1_fc_agent.app:/ask 的流中断了` 加 `NoneType: None`
- **根因**：规格只断言**客人收到什么**：事件的类型和顺序、`error` 的 `message` 里有没有泄漏。日志走的是 stderr，`TestClient` 收不到，所以没有任何一条测试看得见服务端记了什么。③是因为出错时程序从 `for` 里直接跳去 `except`，循环后面那一行走不到；正常结束时它倒是执行了，但那时没有异常可贴
- **修复**：没修。要让测试管日志，可以用 pytest 自带的 `caplog` 夹具拿到日志记录再断言（这个仓库还没用过，后面的课补）
- **教训**：①**改了测试管不到的那一层，测试全绿不说明任何事**，得起服务亲眼看一次 ②"不报错"和"干了它该干的事"是两回事：②③都不报错，只是日志记错了地方 ③和 P011–P015 是同一家族。这个家族的共同点是：有一层东西（客人听到什么、模型说没说完、服务端记了什么）在测试的视野之外。每加一层，就问一句"这层谁在看着"

## P017 · 2026-11-27 · 字段名写死、店规忘了 `join`：100 条测试照样全绿，只有真调用才露馅

- **现象**：`ask_json` 里拼店规的那一行有两种写错，在副本里各改一处实测：①`fields = "city、unit"`（字段名写死，不从表格上读）②`fields = model.model_fields`（忘了 `"、".join`）。两种写法 `tests/test_structured.py` 都是 `10 passed`、全量 `100 passed`。真跑验收脚本（各 2 遍，逐字相同）：①问"上海天气怎么样"照常填对，问"三乘以七等于多少"（表格是 `CalcQuery`）报 `expression: Field required`：店规里只写了 `city、unit`，模型根本不知道有 `expression` 这一格；②不报错，但输出和预期对不上：第一行单位从 `摄氏度` 变成 `celsius`，第二行回 `CalcQuery(expression='3*7')`。因为发出去的店规是 `字段：{'city': FieldInfo(annotation=str, required=True), 'unit': FieldInfo(annotation=str, required=False, default='celsius')}`，120 个字符的字段清单里带着 `default='celsius'`，模型照着它填了
- **根因**：规格里的 `FakeSend` 只看得见**发出去的请求体**，而规格对店规的断言是 `"city" in rule["content"] and "unit" in rule["content"]`（`test_ask_json_sends_json_mode_and_field_names`）。写死的两个字段名过得了；那段 `FieldInfo` 的文字里恰好也有 `city` 和 `unit` 这两个词，同样过得了。4 条 `ask_json` 的测试用的又都是 `WeatherQuery` 一张表，没有一条换一张表
- **修复**：没修（代码本身是对的，这是规格的盲区）。要堵上，加一条测试换一张表（比如 `CalcQuery`），断言店规里有 `expression`、没有 `city`；或者直接断言店规整句等于 `只输出一个 JSON 对象，不要解释。字段：city、unit`
- **教训**：①`in` 这种断言太松：它只说"这个词在"，不说"这个词是怎么来的"。要防"写死"，就让测试换一个输入，看输出跟着变 ②出现"测试全绿 + 真调用结果不对"，先把发出去的请求体原样打印出来看，这次是店规里混进了 120 个字符的程序内部表示 ③和 P011–P016 是同一家族，盲区换到了"提示词长什么样"这一层

## P018 · 2026-11-27 · 工具的参数表里混进了"答案"字段：112 条测试照样全绿，人口数是模型编的，三遍编出两个数

- **现象**：Function Calling 做完，问"上海有多少人口"，`decide` 回 `[PopulationQuery(city='上海', value=24870000)]`，像是查出来的。接着再跑两遍，回的是 `PopulationQuery(city='上海', value=2487)`。同一句话，三遍里两个不同的值，哪一个都没人查过：`run` 对人口表回的是一句写死的话"{城市}人口约 2487 万"，`value` 填什么都没人看。全量 `112 passed`
- **根因**：表格设计错了。`PopulationQuery` 的字段是 `city` 和 `value`，说明文字写的是"城市人口数，必须为正"——把"查出来是多少"做成了让模型填的一格。模型手里只有客人的一句话，抄不到人口数，只能编；校验器只查"是不是正数"，编出来的两个数都过得了。规格里的 `FakeSend` 回的参数是写死的，12 条测试验证的是"模型给的我们解析得了"，没有一条能看见"这个值从哪来"。和 P017 是同一个盲区换了一层：那一次看不见提示词，这一次看不见值的来源
- **修复**：没修，留到 W3-S4。要做的是两件事：参数表里只留"查什么"（`city`），人口数由执行函数去查；再补一条规格，断言 `PopulationQuery` 的字段只有 `city`
- **教训**：①**工具的参数只放模型能从客人话里抄出来的东西**（城市名、算式、日期），要靠外部数据才知道的数（人口、天气、计算结果）一律让执行函数去拿 ②模型填的值分两类：抄来的可以用 Schema 和校验器管，编的测试和校验都管不了，只能靠表格设计不给它编的机会 ③真调用的结果"看着对"不算对：这个 24870000 很像真的，多跑两遍才露馅。数字型的结果至少跑三遍再信

