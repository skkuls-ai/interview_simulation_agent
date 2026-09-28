"""분석 에이전트 smoke test: 데모 샘플로 실제 Gemini 를 호출합니다 (담당 1).

    python -m scripts.prep_smoke                 # JD 분석 + 경험 분석
    python -m scripts.prep_smoke --model gemini-3.7-flash

pytest 에 넣지 않은 이유: 실제 API 를 호출해 시간과 할당량을 씁니다.
결과: 추출 결과, 코드 안전장치가 버린 항목(issues), 호출 시간을 출력하고 var/eval/ 에 JSON 으로 남깁니다.
또 정답 라벨(expected_points.json)의 서류 인용이 경험의 주장 구절로 잡혔는지 미리 확인합니다
(검증 포인트 자체는 STEP 3 에서 만듭니다).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from backend.interview.llm_analysis_agents import LLMAnalysisAgents
from backend.interview.quotes import find_quote
from backend.llm.client import GeminiClient
from backend.llm.settings import LLMSettings
from backend.question_bank.models import QuestionBank

ROOT = Path(__file__).parents[1]
DEMO = ROOT / "data" / "demo"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="analysis 역할 모델 덮어쓰기")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    if args.model:
        os.environ["INTERVIEW_MODEL_ANALYSIS"] = args.model
    settings = LLMSettings.from_env()
    agents = LLMAnalysisAgents(GeminiClient(settings), QuestionBank.load(str(ROOT / "backend/question_bank/question_bank.json")))

    jd, resume, cover = [(DEMO / f"{n}.txt").read_text(encoding="utf-8") for n in ("jd", "resume", "cover_letter")]
    labels = json.loads((DEMO / "expected_points.json").read_text(encoding="utf-8"))

    print(f"모델: {settings.role('analysis').model} (vertex={settings.use_vertex})\n")
    t0 = time.perf_counter()
    with ThreadPoolExecutor(2) as pool:  # 그래프처럼 두 분석을 동시에 실행
        f_jd = pool.submit(agents.analyze_jd, jd)
        f_exp = pool.submit(agents.analyze_experiences, resume, cover)
        company, reqs = f_jd.result()
        exps = f_exp.result()
    wall = time.perf_counter() - t0

    print("=== 회사 정보")
    print(f"  {company.company_name} / {company.role_title}")
    print(f"  가치: {company.mission_or_values}")
    print(f"\n=== 요구사항 {len(reqs)}개")
    for r in reqs:
        print(f"  {r.id} [{r.importance:9}] {r.kind:10} {r.text}  {r.competency_codes}")
    print(f"\n=== 경험 {len(exps)}개")
    for e in exps:
        print(f"  {e.id} [{e.source:12}] {e.title}  {e.competency_codes}")
        for c in e.claimed_results:
            print(f"       · {c}")

    for name in ("analyze_jd", "analyze_experiences"):
        info = agents.last_calls.get(name)
        issues = agents.last_issues.get(name, [])
        took = f"{info.latency_sec:.1f}초, 시도 {info.attempts}회" if info else "LLM 결과 없음"
        print(f"\n=== {name}: {took}, 안전장치 {len(issues)}건")
        for msg in issues:
            print(f"  - {msg}")

    # 정답 라벨의 서류 인용이 경험의 주장 구절로 잡혔는지 (서로 포함 관계면 잡힌 것으로 봄).
    # JD 공백 라벨(L8, L9)은 요구사항 요약에 인용이 남지 않아 여기서는 사람이 위 목록으로 확인합니다.
    print("\n=== 정답 라벨 미리보기 (STEP 3 전 사전 점검)")
    claims: dict[str, list[str]] = {"resume": [], "cover_letter": []}
    for e in exps:
        claims[e.source].extend(e.claimed_results)
    hit = total = 0
    for lab in labels["labels"]:
        doc_sources = [s for s in lab["sources"] if s["doc"] != "jd"]
        if not doc_sources:
            print(f"  ·  {lab['label_id']} {lab['claim_type']:16} (JD 공백: 요구사항 목록에서 확인) {lab['sources'][0]['quote']}")
            continue
        found = [
            any(find_quote(s["quote"], c, min_chars=4) or find_quote(c, s["quote"], min_chars=4) for c in claims[s["doc"]])
            for s in doc_sources
        ]
        total += 1
        hit += all(found)
        mark = "✅" if all(found) else ("◐" if any(found) else "✗")
        print(f"  {mark} {lab['label_id']} {lab['claim_type']:16} {' / '.join(s['quote'] for s in doc_sources)}")
    print(f"  → 서류 라벨 {total}개 중 주장 구절로 모두 잡힌 것 {hit}개")
    print(f"\n전체 소요 {wall:.1f}초 (두 분석 동시 실행)")

    out = ROOT / "var" / "eval" / f"prep_smoke_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "model": settings.role("analysis").model, "wall_sec": round(wall, 2),
        "company": company.model_dump(), "requirements": [r.model_dump() for r in reqs],
        "experiences": [e.model_dump() for e in exps], "issues": agents.last_issues,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"기록: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
