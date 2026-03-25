from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.sheets import get_expenses

app = FastAPI(title="RepeatCosts", version="0.1.0")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/api/expenses")
def api_expenses():
    try:
        return get_expenses()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
def root():
    return FileResponse(str(STATIC_DIR / "index.html"))
