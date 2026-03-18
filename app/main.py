from fastapi import FastAPI

app = FastAPI(title="RepeatCosts", version="0.1.0")


@app.get("/")
def root():
    return {"status": "ok", "message": "RepeatCosts API"}


@app.get("/health")
def health():
    return {"status": "healthy"}
