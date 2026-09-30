"""발표 데모 시나리오(지원자A)로 실제 Gemini 피드백을 만들어 봅니다. J님 PC 에서 실행 (컨테이너 밖).

    cd backend
    python scripts/run_demo_eval.py              # 실제 Gemini 1회 (backend 폴더에서)
    python scripts/run_demo_eval.py --repeat 3   # 3회 실행 후 판정 흔들림과 시간 요약
    python scripts/run_demo_eval.py --fake       # LLM 없이 흐름만 확인 (mock 문구를 그대로 돌려줌)

필요: gcloud auth application-default login, 환경변수 GOOGLE_CLOUD_PROJECT
모델: INTERVIEW_MODEL_EVALUATOR (판정, MEDIUM), INTERVIEW_MODEL_COACH (조언과 질문별, LOW),
      INTERVIEW_MODEL_VALIDATOR (검증, LOW, 15초 제한). 기본은 모두 gemini-3.8-flash

결과는 var/eval/report_<시각>_<회차>.json 에 저장하고, 판정과 호출별 시간을 출력합니다.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_evaluate_runner import M, FakeLLM, make_input  # noqa: E402  데모 입력은 테스트와 같은 시나리오 (지원자A)

from app.nodes.evaluate.runner import Evaluator  # noqa: E402

EXPECTED = {"job_fit": M.JOB_FIT["verdict"], "consistency": M.CONSISTENCY["verdict"]}  # 기대 판정 (mock 기준)


def print_run(i: int, report: dict, ev: Evaluator, elapsed: float, path: Path) -> None:
    t = ev.trace
    print(f"\n==================== {i}회차: {elapsed:.1f}초, LLM 호출 {t.llm_calls}회, 재평가 {t.retried or '없음'}, "
          f"대체값 {t.fallback or '없음'}, 검증 에이전트 실패 {t.reviewer_failed}")
    print("[호출별 시간] (실행 시작 기준 초)")
    print(f"  {'대상':<13}{'시작':>6}{'끝':>7}{'걸린':>7}  {'입력':>7}{'출력':>7}  모델")
    for c in sorted(t.calls, key=lambda c: c["start"]):
        name = c["target"] + (" (재)" if c["retry"] and c["target"] != "reviewer" else "")
        print(f"  {name:<13}{c['start']:>6.1f}{c['end']:>7.1f}{c['end'] - c['start']:>7.1f}  "
              f"{c['input_tokens'] or '-':>7}{c['output_tokens'] or '-':>7}  {c['model'] or '-'}"
              + ("" if c["ok"] else "  실패"))
    for area in ("job_fit", "consistency"):
        f = report[area]
        mark = "" if f["verdict"] == EXPECTED[area] else f"  (기대 {EXPECTED[area]})"
        print(f"\n[{area}] {f['verdict']}{mark}  refs={f['refs']}\n  {f['reason']}")
        for q in f["quotes"]:
            print(f"  인용 {q['question_id']} ({len(q['text'])}자): {q['text']}")
    print("\n[attitude]", json.dumps(report["attitude"]["metrics"]["speech"], ensure_ascii=False))
    for a in report["attitude"]["advice"]:
        print("  조언:", a)
    for q in report["attitude"]["quotes"]:
        print(f"  인용 {q['question_id']}: {q['text']}")
    print("\n[per_question]")
    for p in report["per_question"]:
        print(f"  {p['question_id']} 다음 행동: {p['next_action']}")
    if t.issues:
        print("\n[코드 검증과 검증 에이전트가 지적한 문제]")
        for k, v in t.issues.items():
            for issue in v:
                print(f"  {k}: {issue}")
    print(f"전체 결과: {path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true", help="LLM 없이 실행")
    ap.add_argument("--no-review", action="store_true", help="검증 에이전트 없이 실행")
    ap.add_argument("--repeat", type=int, default=1, help="반복 실행 횟수 (판정 흔들림 확인)")
    args = ap.parse_args()

    if args.fake:
        make_llm, model = FakeLLM, "fake"
    else:
        from app.nodes.evaluate.llm.client import GeminiClient
        from app.nodes.evaluate.llm.settings import LLMSettings

        settings = LLMSettings.from_env()
        client = GeminiClient(settings)
        make_llm = lambda: client  # noqa: E731
        model = f"{settings.role('evaluator').model} / 검증 {settings.role('validator').model}"
    print(f"모델: {model}, {args.repeat}회 실행")

    out_dir = ROOT / "var" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    runs = []
    for i in range(1, args.repeat + 1):
        ev = Evaluator(make_llm(), use_reviewer=not args.no_review)
        t0 = time.perf_counter()
        report = ev.run(make_input())
        elapsed = time.perf_counter() - t0
        path = out_dir / f"report_{stamp}_{i}.json"
        path.write_text(json.dumps({"report": report, "trace": ev.trace.__dict__}, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        print_run(i, report, ev, elapsed, path)
        runs.append((report, ev.trace, elapsed))

    if len(runs) > 1:
        print("\n==================== 요약")
        times = [e for _, _, e in runs]
        print(f"걸린 시간: 중앙값 {statistics.median(times):.1f}초, 최소 {min(times):.1f}, 최대 {max(times):.1f}")
        for area in ("job_fit", "consistency"):
            v = [r[area]["verdict"] for r, _, _ in runs]
            print(f"{area}: {v}  기대와 같음 {sum(x == EXPECTED[area] for x in v)}/{len(v)}")
        by_target: dict[str, list[float]] = {}
        for _, t, _ in runs:
            for c in t.calls:
                by_target.setdefault(c["target"], []).append(c["end"] - c["start"])
        print("대상별 걸린 시간 중앙값: " + ", ".join(f"{k} {statistics.median(v):.1f}초" for k, v in by_target.items()))
        print(f"재평가가 일어난 회차: {sum(bool(t.retried) for _, t, _ in runs)}/{len(runs)}")


if __name__ == "__main__":
    main()
