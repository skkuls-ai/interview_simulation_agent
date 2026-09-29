"""분석 에이전트 smoke test: 데모 샘플로 실제 Gemini 를 호출합니다 (담당 1).

    python -m scripts.prep_smoke                 # JD 분석 + 경험 분석
    python -m scripts.prep_smoke --model gemini-3.7-flash

pytest 에 넣지 않은 이유: 실제 API 를 호출해 시간과 할당량을 씁니다.
결과: 추출 결과, 코드 안전장치가 버린 항목(issues), 호출 시간을 출력하고 var/eval/ 에 JSON 으로 남깁니다.
또 정답 라벨(expected_points.json)의 주장이 경험의 주장 구절로 잡혔는지 미리 확인합니다
(검증 포인트·요구사항 공백 채점은 STEP 3 에서 합니다).
입력은 docs 기준 서류 4종(이력서, 채용공고, 직무기술서, 자기소개서)입니다.
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

    posting, description, resume, cover = [
        (DEMO / f"{n}.txt").read_text(encoding="utf-8")
        for n in ("job_posting", "job_description", "resume", "cover_letter")
    ]
    # 현재 analyze_jd 인터페이스(담당 3의 이전 구조)는 공고 텍스트 하나만 받으므로 두 문서를 이어 붙입니다.
    # docs/04 계약으로 옮기면 채용공고·직무기술서를 따로 넘기고 Requirement.source_doc 으로 구분합니다.
    jd = f"[채용공고]\n{posting}\n\n[직무기술서]\n{description}"
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

    # 정답 라벨의 주장(expected_claims)이 주장 구절로 잡혔는지 (서로 포함 관계면 잡힌 것으로 봄).
    # 검증 포인트(CP)와 요구사항 공백(G)은 STEP 3 에서 채점합니다. 공백 라벨은 위 요구사항 목록으로 사람이 확인합니다.
    print("\n=== 정답 라벨 미리보기: 주장 포착 (검증 포인트·공백 채점은 STEP 3)")
    claims: dict[str, list[str]] = {"resume": [], "cover_letter": []}
    for e in exps:
        claims[e.source].extend(e.claimed_results)
    hit = 0
    for lab in labels["expected_claims"]:
        ok = any(find_quote(lab["quote"], c, min_chars=4) or find_quote(c, lab["quote"], min_chars=4)
                 for c in claims[lab["source_doc"]])
        hit += ok
        print(f"  {'✅' if ok else '✗'} {lab['label_id']:4} {'/'.join(lab['types']):15} [{lab['source_doc']}] {lab['quote']}")
    print(f"  → 주장 {len(labels['expected_claims'])}개 중 {hit}개 포착")
    print("\n=== 요구사항 공백 라벨 (요구사항 목록에 있는지 사람이 확인)")
    for g in labels["expected_gaps"]:
        print(f"  ·  {g['label_id']} [{g['source_doc']}] {g['quote']}")
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
