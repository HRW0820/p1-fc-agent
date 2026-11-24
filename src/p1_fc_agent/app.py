# 最小 FastAPI 应用
from fastapi import FastAPI
from pydantic import BaseModel, Field
from pydantic import field_validator


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