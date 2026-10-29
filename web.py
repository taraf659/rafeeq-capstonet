# /// script
# requires-python = ">=3.11"
# dependencies = ["fastapi>=0.115", "uvicorn>=0.32", "openai>=3.30", "pydantic>=2.12", "python-dotenv>=1.1", "pandas>=2.2", "mcp>=2.3"]
# ///
"""Small browser UI for Rafeeq.

Run locally:
  uv run web.py
Then open http://127.0.0.1:8000
"""
from __future__ import annotations
import argparse
from contextlib import asynccontextmanager
from pathlib import Path
import sys
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import agentkit as K  # noqa: E402
import madar  # noqa: E402
from rafeeq import CONFIGS, OUT, cap_result, mcp_policy_tool, mcp_server, local_tools, permission  # noqa: E402

class AskRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    confirm_writes: bool = False

class AskResponse(BaseModel):
    answer: str
    tools: list[str]
    stopped: str
    write_approval: bool

@asynccontextmanager
async def lifespan(app: FastAPI):
    with K.MCPBridge(mcp_server()) as bridge:
        app.state.bridge = bridge
        yield

app = FastAPI(title="Rafeeq Secure Municipal Agent", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")

@app.get("/", response_class=FileResponse)
def index():
    return FileResponse(ROOT / "web" / "index.html")

@app.get("/health")
def health():
    return {"status": "ok", "service": "rafeeq", "mcp": True}

@app.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest):
    bridge = getattr(app.state, "bridge", None)
    if bridge is None:
        raise HTTPException(status_code=503, detail="MCP bridge is not ready")
    m = madar.Madar(OUT / "web-db", actor="web-user")
    def approve(name: str, args: dict) -> bool:
        return bool(req.confirm_writes)
    try:
        tools = local_tools(m, mcp_policy_tool(bridge))
        run = K.run_agent(req.message, tools, system=CONFIGS["A"]["system"],
                          max_steps=8, max_cost=0.05, permission=permission,
                          approve=approve, after_tool=cap_result, verbose=False)
    except Exception as exc:  # keep implementation details out of the browser
        raise HTTPException(status_code=502, detail=f"Agent request failed: {type(exc).__name__}") from exc
    return AskResponse(answer=run.final or f"(stopped: {run.stopped})",
                       tools=[name for name, _ in run.tool_calls], stopped=run.stopped,
                       write_approval=req.confirm_writes)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
