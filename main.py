from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from agent import run_agent
from dotenv import load_dotenv
import uvicorn
import os
from shared_store import url_time, BASE64_STORE
import time

load_dotenv()

EMAIL = os.getenv("EMAIL") 
SECRET = os.getenv("SECRET")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
START_TIME = time.time()
@app.get("/healthz")
def healthz():
    """Simple liveness check."""
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME)
    }

@app.post("/solve")
async def solve(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not data:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    url = data.get("url")
    secret = data.get("secret")
    if not url or not secret:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    if secret != SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")
    url_time.clear() 
    BASE64_STORE.clear()  
    print("Verified starting the task...")
    os.environ["url"] = url
    os.environ["offset"] = "0"
    url_time[url] = time.time()
    background_tasks.add_task(run_agent, url)

    return JSONResponse(status_code=200, content={"status": "ok"})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)