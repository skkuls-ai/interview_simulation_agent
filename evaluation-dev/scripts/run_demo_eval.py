"""데모 시나리오로 실제 Gemini 피드백을 한 번 만들어 봅니다. J님 PC 에서 실행 (컨테이너 밖).

    cd evaluation-dev
    python scripts/run_demo_eval.py              # 실제 Gemini
    python scripts/run_demo_eval.py --fake       # LLM 없이 흐름만 확인 (mock 문구를 그대로 돌려줌)

필요: gcloud auth application-default login, 환경변수 GOOGLE_CLOUD_PROJECT
모델: INTERVIEW_MODEL_EVALUATOR (기본 gemini-3.8-flash), INTERVIEW_MODEL_VALIDATOR (기본 gemini-3.7-flash)

결과는 var/eval/report_<시각>.json 에 저장하고, 판정과 호출 기록을 요약해 출력합니다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_runner import FakeLLM, make_input  # noqa: E402  데모 입력은 테스트와 같은 시나리오

from evaluate.runner import Evaluator  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true", help="LLM 없이 실행")
    ap.add_argument("--no-review", action="store_true", help="검증 에이전트 없이 실행")
    args = ap.parse_args()

    if args.fake:
        llm, model = FakeLLM(), "fake"
    else:
        from evaluate.llm.client import GeminiClient
        from evaluate.llm.settings import LLMSettings

        settings = LLMSettings.from_env()
        llm = GeminiClient(settings)
        model = f"{settings.role('evaluator').model} / 검증 {settings.role('validator').model}"

    steps = []
    ev = Evaluator(llm, use_reviewer=not args.no_review,
                   on_step=lambda s, st: steps.append(f"{time.perf_counter() - t0:5.1f}s {s} {st}"))
    t0 = time.perf_counter()
    report = ev.run(make_input())
    elapsed = time.perf_counter() - t0

    out_dir = ROOT / "var" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"report_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    t = ev.trace
    print(f"모델: {model}")
    print(f"걸린 시간 {elapsed:.1f}초, LLM 호출 {t.llm_calls}회, 재평가 {t.retried or '없음'}, "
          f"대체값 {t.fallback or '없음'}, 검증 에이전트 실패 {t.reviewer_failed}")
    for area in ("job_fit", "consistency"):
        f = report[area]
        print(f"\n[{area}] {f['verdict']}  refs={f['refs']}\n  {f['reason']}")
        for q in f["quotes"]:
            print(f"  인용 {q['question_id']}: {q['text']}")
    print("\n[attitude]", json.dumps(report["attitude"]["metrics"]["speech"], ensure_ascii=False))
    for a in report["attitude"]["advice"]:
        print("  조언:", a)
    print("\n[per_question]")
    for p in report["per_question"]:
        print(f"  {p['question_id']} 다음 행동: {p['next_action']}")
    if t.issues:
        print("\n[코드 검증과 검증 에이전트가 지적한 문제]")
        for k, v in t.issues.items():
            for i in v:
                print(f"  {k}: {i}")
    print(f"\n단계 기록: {' | '.join(steps)}")
    print(f"전체 결과: {path}")


if __name__ == "__main__":
    main()
