from fastapi import FastAPI

app = FastAPI(title="ProofInterview")


@app.get("/api/health")
def health():
    return {"status": "ok"}
