# 最小 FastAPI 应用
from fastapi import FastAPI,HTTPException, Header, Depends
from pydantic import BaseModel, Field, field_validator
from p1_fc_agent.tools import WeatherQuery, PopulationQuery, CalcQuery, run_calculator, format_validation_error
import os
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi import Request
from fastapi.responses import StreamingResponse
from p1_fc_agent.sse import sse, token_stream



app = FastAPI(title="demo")

@app.get("/health")          # 菜单上挂一道菜：GET 方法的 /health
async def health():          # 谁做这道菜：这个函数
    return {"status": "ok"}  # 端上来什么：这个 dict 自动变 JSON

class EchoRequest(BaseModel):
    message: str = Field(min_length=1) 
    repeat: int = Field(default=1, ge=1, le=5)
    model_config = {"extra": "forbid"}

    @field_validator("message")
    @classmethod
    def clean_message(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("消息不能为空白")
        return v
    
@app.post("/echo")
async def echo(req: EchoRequest):
    return {"message": req.message, "repeat": req.repeat}


TOOLS = {
    "weather": ("查城市天气", WeatherQuery),
    "population": ("查城市人口", PopulationQuery),
    "calculator": ("四则运算", CalcQuery),
}

@app.get("/tools/{tool_name}")
async def tool_info(tool_name: str):              # 路径参数：/tools/weather 里的 "weather"
    if tool_name not in TOOLS:
        raise HTTPException(status_code=404, detail=f"未知工具: {tool_name}，可用: {', '.join(sorted(TOOLS))}")
    description, model = TOOLS[tool_name]
    return {"name": tool_name, "description": description, "parameters": model.model_json_schema()}

#@app.post("/calculator")
#async def calculator(req: CalcQuery):
#    return {"result": run_calculator(req.expression)}

# ① 配置：服务从哪读"正确的 key"
class Settings(BaseModel):
    api_key: str

def get_settings() -> Settings:
    return Settings(api_key=os.environ.get("P1_API_KEY", "dev-key"))

# ② 查卡函数：它自己也需要 ①，所以参数里又写了一个 Depends —— 依赖可以套依赖
async def require_api_key(
    x_api_key: str | None = Header(default=None),              # 从请求头里取 X-API-Key
    settings: Settings = Depends(get_settings),                # "我需要配置"
) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="无效的 API Key")

# ③ 路由：声明"我需要查卡"，返回值不要（下划线）
@app.post("/calculator")
async def calculator(req: CalcQuery, _: None = Depends(require_api_key)):
    return {"result": run_calculator(req.expression)}

async def readable_validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors()),       # 原有的结构照旧保留
                 "message": format_validation_error(exc)},      # 新增：一句人话
    )

app.add_exception_handler(RequestValidationError, readable_validation_handler)

async def unhandled_error_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})

app.add_exception_handler(Exception, unhandled_error_handler)

class StreamRequest(BaseModel):
    text: str = Field(min_length=1)
    delay: float = Field(default=0.05, ge=0, le=1)
    model_config = {"extra": "forbid"}

    @field_validator("text")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text 不能是空白")
        return v
@app.post("/stream")
async def stream(req: StreamRequest):
    return StreamingResponse(token_stream(req.text, req.delay), media_type="text/event-stream",
                         headers={"Cache-Control": "no-cache"})