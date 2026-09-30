from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import answers, interviews, report
from .errors import register_error_handlers

app = FastAPI(title="ProofInterview")

# 개발 편의용. Docker에서는 프런트가 /api를 프록시하므로 CORS가 필요 없다.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
register_error_handlers(app)

app.include_router(interviews.router)
app.include_router(answers.router)
app.include_router(report.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
