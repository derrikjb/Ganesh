from fastapi import FastAPI

app = FastAPI(title="Ganesh API")

@app.get("/health")
async def health():
    return {"status": "ok"}
