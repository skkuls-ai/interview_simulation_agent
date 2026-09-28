"""터미널에서 전체 면접 흐름을 체험합니다 (스텁 에이전트, 텍스트 입력).

    python -m scripts.demo_cli                       # 문서 없이
    python -m scripts.demo_cli --jd jd.txt --resume resume.pdf --mode practice

답변 시간은 질문이 표시된 뒤 Enter 를 누를 때까지의 실제 시간으로 잽니다 (준비시간 5초 제외).
빈 줄을 입력하면 무응답으로 처리됩니다. 스텁은 80자보다 짧은 답변에 꼬리질문을 합니다.
"""

from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

from backend.interview.agents import StubAnalysisAgents, StubEvaluationAgents, StubInterviewAgents
from backend.interview.serde import make_sqlite_checkpointer
from backend.interview.state import Mode, SessionConfig
from backend.interview.timing import fmt
from backend.question_bank.models import QuestionBank
from backend.service.consent import ConsentRecord
from backend.service.documents import DocumentStore
from backend.service.session_service import SessionService
from backend.service.store import Store

ROOT = Path(__file__).parents[1]


def on_event(sid, ev):
    if ev.type == "interviewer_thinking":
        print(f"  … {ev.message}")
    elif ev.type == "question_feedback":
        score = f"{ev.evaluation.score}점" if ev.evaluation.score is not None else "판단 보류"
        print(f"  [연습 모드 피드백] {ev.thread_id}: {score}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jd")
    ap.add_argument("--resume")
    ap.add_argument("--cover-letter")
    ap.add_argument("--mode", choices=["real", "practice"], default="real")
    ap.add_argument("--data-dir", default=None, help="지정하면 결과와 세션이 저장되어 재개할 수 있음")
    ap.add_argument("--llm", action="store_true", help="꼬리질문 판단에 Gemini 사용 (Vertex 설정 필요)")
    args = ap.parse_args()

    data = Path(args.data_dir or tempfile.mkdtemp())
    data.mkdir(parents=True, exist_ok=True)
    bank = QuestionBank.load(str(ROOT / "backend/question_bank/question_bank.json"))
    if args.llm:
        from backend.interview.llm_agents import HybridInterviewAgents
        from backend.llm.client import GeminiClient

        from backend.interview.evaluation import gemini_evaluation_agents

        llm = GeminiClient()
        interview_agents = HybridInterviewAgents(bank, llm)
        evaluation_agents = gemini_evaluation_agents(bank, llm)
    else:
        interview_agents = StubInterviewAgents(bank)
        evaluation_agents = StubEvaluationAgents()
    svc = SessionService(
        bank, StubAnalysisAgents(), interview_agents, evaluation_agents,
        Store(data / "app.db"), DocumentStore(data / "uploads"), make_sqlite_checkpointer(str(data / "cp.db")),
        on_event=on_event,
    )
    docs = {"jd": args.jd, "resume": args.resume, "cover_letter": args.cover_letter}
    consent = ConsentRecord(microphone=True, camera=False, documents=any(docs.values()), store_results=True)
    sid = svc.create_session(consent, SessionConfig(mode=Mode(args.mode)))
    for kind, path in docs.items():
        if path:
            svc.upload_document(sid, kind, Path(path).name, Path(path).read_bytes())

    print("서류를 분석하고 있습니다…")
    bp = svc.analyze(sid)
    g = bp.guide
    print("\n=== 면접 구성 안내 ===")
    for item in g.items:
        print(f"  {item.topic}: {item.count}문항" + (f" ({item.note})" if item.note else ""))
    print(f"  예상 소요 시간: {g.expected_minutes[0]}~{g.expected_minutes[1]}분")
    for rule in g.answer_rules:
        print(f"  · {rule}")

    prompt = svc.start(sid)
    while True:
        if prompt.type == "await_ready":
            input("\n준비가 되면 Enter 를 눌러 면접을 시작하세요 (준비시간) ")
            payload = {"action": "start"}
        elif prompt.type == "no_response":
            c = input(f"\n{prompt.message} [r=다시 답변 / s=넘어가기] ").strip().lower()
            payload = {"choice": "skip" if c.startswith("s") else "retry"}
        else:
            print(f"\n면접관: {prompt.lead_in or ''}")
            print(f"[질문] {prompt.text}")
            print(f"  (준비시간 {prompt.think_time_sec}초 후 답변시간 시작, 권장 {fmt(prompt.soft_limit_sec)})")
            t0 = time.monotonic()
            text = input("> ")
            dur = time.monotonic() - t0
            if dur > prompt.soft_limit_sec:
                print(f"  ⚠ 권장 시간 초과 +{fmt(dur - prompt.soft_limit_sec)}")
            payload = {"text": text, "answer_duration_sec": round(dur, 1), "sequence": prompt.sequence}

        res = svc.act(sid, payload)
        if res.completed:
            break
        prompt = res.prompt

    d = res.completed["detail"]
    chro, fb = d["chro_decision"], d["final_feedback"]
    print(f"\n=== 종합 판정: {chro['decision']} (평균 {chro['average_score']}) ===")
    for c in chro["rule_checks"]:
        print(f"  {'통과' if c['passed'] else '미달'}  {c['name']}: {c['detail']}")
    print("\n[시간 관리]")
    for m in fb["time_management"]["messages"]:
        print(f"  {m}")
    print(f"\n결과 저장: {'예' if res.completed['stored'] else '아니오'} / 문서 삭제 완료")
    svc.shutdown()


if __name__ == "__main__":
    main()
