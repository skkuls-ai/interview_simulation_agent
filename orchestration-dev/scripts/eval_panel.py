"""평가자 3명 패널을 실제 Gemini 로 평가합니다. J님 PC 에서 실행하세요.

    python -m scripts.eval_panel --repeat 2

답변 수준을 알고 있는 시나리오(강함, 약함, 장황하지만 빈약함 등)를 채점해
- 점수가 기대 범위에 드는지
- 같은 답변을 반복 채점해도 점수가 흔들리지 않는지 (반복 간 차이)
- 무효 판정, 재평가, 판단 보류가 얼마나 생기는지
- 문항 하나 평가에 걸리는 시간
을 출력하고, var/eval/ 에 전체 기록(JSONL)을 남깁니다.
기대 범위는 제가 정한 초안입니다. J님이 직접 매긴 점수로 바꾸면 그게 기준 답변 세트가 됩니다.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from backend.interview.agents import StubAnalysisAgents
from backend.interview.analysis_graph import build_analysis_graph
from backend.interview.evaluation import stub_panel_agents
from backend.interview.state import QuestionThread, SessionConfig, Turn
from backend.question_bank.models import QuestionBank

ROOT = Path(__file__).parents[1]
BANK = QuestionBank.load(str(ROOT / "backend/question_bank/question_bank.json"))


@dataclass
class Case:
    name: str
    qid: str
    answers: list[str]  # 첫 답변과 꼬리질문 답변들
    expected: tuple[int, int]  # 기대 점수 범위 (포함)


CASES = [
    Case("강한 경험 답변", "Q001", [
        "신규 서비스 출시 3주 전에 핵심 개발자가 퇴사해 팀원 다섯 명이 일정 연기를 이야기했습니다. 저는 남은 기능 40개를 "
        "필수와 선택으로 나누는 표를 만들어 팀에 제안했고, 매일 아침 15분씩 막힌 부분을 함께 풀었습니다. 팀원들은 처음엔 "
        "회의적이었지만 첫 주에 필수 기능 절반을 끝내자 분위기가 바뀌었습니다. 결국 예정일에 출시했고 첫 달 사용자 목표의 "
        "120%를 달성했습니다. 어려울수록 범위를 좁혀 작은 성공을 먼저 만드는 것이 중요하다는 걸 배웠습니다."], (4, 5)),
    Case("본인 행동 없는 답변", "Q001", [
        "팀 프로젝트가 막혀서 다들 힘들어했는데, 우리 팀이 다 같이 노력해서 잘 마무리했습니다. 결과도 좋았습니다.",
        "팀원들이 서로 도우면서 해결했던 것 같습니다."], (1, 2)),
    Case("장황하지만 빈약", "Q001", [
        "그 당시를 떠올려 보면 정말 여러 가지 일이 있었는데요, 일단 분위기가 많이 안 좋았고 다들 지쳐 있었습니다. "
        "저도 사실 많이 힘들었고요, 그래도 끝까지 해야 한다는 생각이 있었습니다. 무엇보다 팀워크가 중요하다고 생각하고 "
        "항상 긍정적인 마음을 가지려고 노력하는 편입니다. 어떤 일이든 포기하지 않는 것이 제 장점이라고 생각합니다. "
        "결국 어떻게든 잘 끝났던 것으로 기억합니다."], (1, 2)),
    Case("중간 수준 (결과 약함)", "Q006", [
        "HR 분석 역량을 키우려고 2년 동안 퇴근 후 매일 SQL과 통계를 공부했고, 사내 데이터로 이직률 분석을 직접 해 봤습니다.",
        "아직 회사에서 공식적으로 쓰이지는 않았고, 팀장님께 한 번 보고드린 정도입니다."], (2, 3)),
    Case("강한 상황 답변", "Q005", [
        "먼저 팀장님과 1:1 면담을 요청해 제 업무 방식에서 개선할 점이 있는지 여쭙겠습니다. 팀장님이 회사에서 인정받는 분인 "
        "만큼 제가 놓친 부분이 있을 수 있다고 보기 때문입니다. 동시에 현재 업무 목록과 예상 소요 시간을 정리해, 우선순위를 "
        "함께 정해 달라고 요청하겠습니다. 그래도 부당한 배분이 계속되면 기록을 근거로 다시 논의하고, 그 과정에서도 맡은 일의 "
        "품질은 유지해 신뢰를 쌓겠습니다. 이렇게 하면 오해가 풀리고 업무량도 합리적으로 조정될 것이라고 봅니다."], (4, 5)),
    Case("약한 상황 답변", "Q005", ["그냥 시키는 대로 다 하겠습니다.", "팀장님이니까요."], (1, 2)),
]


def build_thread(case: Case) -> QuestionThread:
    q = BANK.get(case.qid)
    turns = [Turn(speaker="interviewer", kind="main", text=q.text)]
    for i, a in enumerate(case.answers):
        if i > 0:
            turns.append(Turn(speaker="interviewer", kind="generated_follow_up", text="조금 더 구체적으로 말씀해 주시겠습니까?"))
        turns.append(Turn(speaker="candidate", kind="answer", text=a))
    return QuestionThread(thread_id=q.id, stage="main", question_id=q.id, category_code="performance",
                          competency_code=q.competency_code, closed=True, turns=turns)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=2, help="같은 답변을 몇 번 채점할지 (일관성 확인)")
    ap.add_argument("--fake", action="store_true", help="LLM 없이 스크립트 동작만 확인")
    args = ap.parse_args()

    if args.fake:
        agents, model = stub_panel_agents(BANK), "fake"
    else:
        from backend.interview.evaluation import gemini_evaluation_agents
        from backend.llm.client import GeminiClient
        from backend.llm.settings import LLMSettings

        settings = LLMSettings.from_env()
        agents, model = gemini_evaluation_agents(BANK, GeminiClient(settings)), settings.role("evaluator").model

    bp = build_analysis_graph(BANK, StubAnalysisAgents()).invoke({"config": SessionConfig(), "seed": 1})["blueprint"]
    out_dir = ROOT / "var" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"panel_{model}_{datetime.now():%Y%m%d_%H%M%S}.jsonl"

    in_range = total = retried = invalid = undetermined = disputed = 0
    latencies, spreads = [], []
    print(f"평가 모델: {model}, 시나리오 {len(CASES)}개 × {args.repeat}회 (회당 평가자 3명)\n")
    with log_path.open("w", encoding="utf-8") as log:
        for case in CASES:
            q, th = BANK.get(case.qid), build_thread(case)
            scores = []
            for _ in range(args.repeat):
                t0 = time.perf_counter()
                ev = agents.evaluate_thread(q, th, bp, [])
                latencies.append(time.perf_counter() - t0)
                total += 1
                ok = ev.score is not None and case.expected[0] <= ev.score <= case.expected[1]
                in_range += ok
                retried += sum(m.re_evaluated for m in ev.panel)
                invalid += sum(not m.valid for m in ev.panel)
                undetermined += ev.status == "undetermined"
                disputed += ev.status == "disputed"
                scores.append(ev.score)
                log.write(json.dumps({"case": case.name, "ok": ok, "latency": round(latencies[-1], 1),
                                      "evaluation": ev.model_dump(mode="json")}, ensure_ascii=False) + "\n")
            valid_scores = [s for s in scores if s is not None]
            if len(valid_scores) > 1:
                spreads.append(max(valid_scores) - min(valid_scores))
            panel_scores = [m.score for m in ev.panel]
            print(f"[{'통과' if all(case.expected[0] <= (s or 0) <= case.expected[1] for s in scores) else '확인'}] "
                  f"{case.name}: 점수 {scores} (기대 {case.expected[0]}~{case.expected[1]}), 마지막 평가자별 {panel_scores}")

    lat = sorted(latencies)
    print(f"\n기대 범위 적중 {in_range}/{total} ({in_range / total:.0%})")
    if spreads:
        print(f"반복 채점 간 최대 차이 평균 {statistics.mean(spreads):.2f}점 (0에 가까울수록 일관됨)")
    print(f"평가자 무효 {invalid}회, 재평가 {retried}회, 평가자 의견 차이(2점 이상) {disputed}회, 판단 보류 {undetermined}회")
    print(f"문항당 평가 시간 중앙값 {statistics.median(lat):.1f}초, 최대 {lat[-1]:.1f}초 (백그라운드라 면접 진행과 무관)")
    print(f"평가 기록: {log_path}")


if __name__ == "__main__":
    main()
