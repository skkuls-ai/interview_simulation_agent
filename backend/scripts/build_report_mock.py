"""report.json, report_edge.json 생성 스크립트 (담당 E, W-14).

발표 데모 샘플 지원자A(shared/mock/sample_inputs.json, 9/30 C 결정) 기준입니다.
질문은 session_ready.json 에서 읽고, 인용 위치(start, end)는 코드로 계산하고, 태도 측정값은
app/nodes/evaluate/attitude.py 로 계산합니다. 만든 뒤 계약 규칙으로 스스로 검사합니다.
답변이나 피드백 문구를 고치려면 이 파일을 고친 뒤 다시 실행하세요.

    python scripts/build_report_mock.py    # backend 폴더에서. shared/mock/report.json, report_edge.json 생성 + 검사

같은 데이터를 러너 테스트(tests/test_evaluate_runner.py)와 실측 스크립트(run_demo_eval.py)가 입력으로 씁니다.
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE.parents[1] / "shared" / "mock"  # 결과 위치, 입력(sample_inputs.json, session_ready.json)도 여기서 읽음
sys.path.insert(0, str(HERE.parent))
from app.nodes.evaluate.attitude import attitude_metrics  # noqa: E402  측정값은 실제 계산 모듈로
from app.schemas.state import Answer  # noqa: E402

SESSION_ID = "S-3f2a9c1e"
INPUTS = json.loads((OUT / "sample_inputs.json").read_text(encoding="utf-8"))
READY = json.loads((OUT / "session_ready.json").read_text(encoding="utf-8"))
DOC_TEXT = {"resume": INPUTS["resume_text"], "job_posting": INPUTS["job_posting_text"],
            "job_description": INPUTS["job_description_text"], "cover_letter": INPUTS["cover_letter_text"]}

# ------------------------------------------------------------------ 규칙 (9/29 C-D 테스트에서 정함)

FORBIDDEN = re.compile(r"합격|불합격|채용 점수|상위 ?\d+ ?%|자신감|진실성|거짓|긴장|불안")  # T-013


# ------------------------------------------------------------------ 분석 결과 (A 가 만들 모양, ID 는 mock 용)
# 문장은 sample_inputs.json 원문 그대로 (검사함). 리포트에는 판정과 질문별 피드백이 가리키는 것만 들어감.

REQUIREMENTS = [
    {"requirement_id": "RQ-001", "text": "Python 활용 능력", "kind": "SKILL", "source_doc": "job_posting"},
    {"requirement_id": "RQ-002", "text": "REST API 개발 경험", "kind": "SKILL", "source_doc": "job_posting"},
    {"requirement_id": "RQ-003", "text": "벡터 검색 또는 RAG 이해", "kind": "SKILL", "source_doc": "job_posting"},
    {"requirement_id": "RQ-004", "text": "LangGraph 등 워크플로 프레임워크 사용 경험", "kind": "SKILL", "source_doc": "job_posting"},
    {"requirement_id": "RQ-005", "text": "검색 품질 평가 경험", "kind": "SKILL", "source_doc": "job_posting"},
    {"requirement_id": "RQ-006", "text": "RAG 파이프라인의 검색 정확도를 측정하고 개선한다", "kind": "DUTY",
     "source_doc": "job_description"},
    {"requirement_id": "RQ-007", "text": "LangGraph로 여러 단계의 LLM 호출 흐름을 설계하고 오류 상황을 처리한다", "kind": "DUTY",
     "source_doc": "job_description"},
    {"requirement_id": "RQ-008", "text": "문제의 원인을 숫자로 확인하고 끝까지 개선하는 사람", "kind": "TALENT",
     "source_doc": "job_posting"},
]
CLAIMS = [
    {"claim_id": "CL-001", "text": "RAG 검색 정확도를 20% 개선했습니다", "source_doc": "resume"},
    {"claim_id": "CL-002", "text": "팀 프로젝트에서 백엔드 API 설계와 일정 조율을 맡았습니다", "source_doc": "resume"},
    {"claim_id": "CL-003", "text": "평가용 질문 50개를 직접 만들어 개선 전후 결과를 비교했습니다", "source_doc": "resume"},
    {"claim_id": "CL-004", "text": "의견이 갈릴 때는 각자 근거를 정리해 데이터로 비교한 뒤 결정했습니다", "source_doc": "cover_letter"},
    {"claim_id": "CL-005", "text": "LangGraph 학습 중", "source_doc": "resume"},
    {"claim_id": "CL-006", "text": "크롤링한 레시피 1,000건을 정리해 검색 API를 만들었습니다", "source_doc": "resume"},
]
CHECKPOINTS = [
    {"checkpoint_id": "CP-001", "title": "검색 정확도 20% 측정 기준", "claim_ids": ["CL-001", "CL-003"],
     "what_to_verify": "20%를 어떤 평가 데이터와 지표로 쟀는지"},
    {"checkpoint_id": "CP-002", "title": "팀 프로젝트 역할과 의견 조율 방식", "claim_ids": ["CL-002", "CL-004"],
     "what_to_verify": "일정 조율과 의견 조율에서 본인이 직접 한 일"},
    {"checkpoint_id": "CP-003", "title": "LangGraph 학습 수준", "claim_ids": ["CL-005"],
     "what_to_verify": "워크플로 프레임워크를 어디까지 이해하고 있는지"},
]
QUESTION_CPS = {"Q-1": ["CP-001"], "Q-2": ["CP-002"], "Q-3": ["CP-002"], "Q-4": ["CP-001"], "Q-5": ["CP-003"]}

# ------------------------------------------------------------------ 답변 (질문은 session_ready.json)
# 받아쓰기 결과처럼 군말을 남겼음. Q-3 은 1분 30초에서 끊김 (shared/mock/README 시나리오).

ANSWERS = {
    "Q-1": {
        "answer_text": "안녕하세요, 검색 기반 AI 서비스를 만들어 온 신입 개발자 지원자입니다. 학부 프로젝트에서 사내 문서 질의응답 챗봇을 "
                       "만들며 RAG 검색 정확도를 20% 개선한 경험이 있습니다. 청크 크기와 리랭킹을 바꿔 가며 평가용 질문 50개로 결과를 "
                       "비교했습니다. 음, 팀에서는 백엔드 API 설계와 일정 조율을 맡았고, 레시피 추천 서비스에서는 레시피 1,000건으로 "
                       "검색 API를 만들어 봤습니다. 결과를 숫자로 확인하는 습관을 살려서 가상테크의 사내 지식 검색 서비스를 개선하는 데 "
                       "기여하고 싶습니다.",
        "duration_sec": 40.4, "timed_out": False,
        "delivery": {"measurable": True, "frontal_ratio": 0.84, "gaze_away_count": 2},
    },
    "Q-2": {
        "answer_text": "네, 말씀드리겠습니다. 어 그러니까 음 팀에서 함께 했던 것 같습니다. 챗봇 프로젝트에서 청크를 작게 나눌지 크게 "
                       "나눌지를 두고 의견이 갈렸습니다. 어, 의견이 갈렸을 때는 각자 근거를 정리해서 다시 이야기했던 것 같습니다. 음, "
                       "저는 회의 일정을 잡고 이야기를 정리하는 역할을 했던 것 같고요. 결국 데이터로 비교해 결정했습니다.",
        "duration_sec": 30.2, "timed_out": False,
        "delivery": {"measurable": True, "frontal_ratio": 0.70, "gaze_away_count": 4},
    },
    "Q-3": {
        "answer_text": "일정이 촉박했던 팀 프로젝트에서 필수 기능부터 먼저 만들고 나머지는 뒤로 미루자고 제안했습니다. 챗봇 프로젝트 마지막 "
                       "3주 동안 기능 목록이 열두 개였는데, 어, 시연에 꼭 필요한 기능이 무엇인지 팀원들과 먼저 골랐습니다. 문서 업로드, "
                       "질문 답변, 근거 문서 표시 이 세 가지를 필수로 정했고요, 음, 관리자 화면이나 답변 평가 버튼 같은 기능은 뒤로 "
                       "미뤘습니다. 저는 매일 아침 십 분씩 진행 상황을 공유하는 자리를 만들어서 막힌 부분을 바로 이야기하게 했습니다. "
                       "어, 중간에 리랭커를 붙이는 작업이 예상보다 오래 걸려서 제가 평가 스크립트를 먼저 만들어 두고 다른 팀원이 "
                       "리랭커를 맡는 식으로 나눴습니다. 그 뒤로는 제가 매일 평가 스크립트를 돌려서 정확도가 떨어지지 않았는지 확인하고 "
                       "결과를 팀에 공유했습니다. 미룬 기능과 그 이유는 공유 문서에 적어 두어서 나중에 발표 자료를 만들 때도 그대로 "
                       "썼습니다. 그렇게 핵심 기능은 기한 안에 끝냈지만 마지막에는 테스트 시간이 부족해서 음, "
                       "발표 전날에 오류가 하나 나왔는데 그걸",
        "duration_sec": 90.0, "timed_out": True,
        "delivery": {"measurable": True, "frontal_ratio": 0.76, "gaze_away_count": 5},
    },
    "Q-4": {
        "answer_text": "정확도는 평가용 질문 50개에 대해 정답 문서가 상위 3개 안에 들어오는 비율로 측정했습니다. 처음에는 50개 중 30개가 "
                       "들어왔는데, 청크 크기를 조정하고 리랭커를 추가해서 36개로, 기존 대비 20% 높아졌습니다. 어, 청크는 500자에서 "
                       "300자로 줄이고 앞뒤 문장을 조금씩 겹치게 했습니다. 평가용 질문은 제가 실제 사내 문서를 읽고 직접 "
                       "만들었습니다. 다만 LangGraph 같은 워크플로 도구는 써 보지 못했습니다.",
        "duration_sec": 34.3, "timed_out": False,
        "delivery": {"measurable": True, "frontal_ratio": 0.81, "gaze_away_count": 3},
    },
    "Q-5": {
        "answer_text": "LangGraph는 직접 써 보지 않았지만 상태를 하나의 객체로 두고 각 노드가 읽고 쓰는 구조로 이해하고 있습니다. 음, "
                       "그래서 질문, 검색 결과, 답변 초안을 하나의 상태에 담고, 단계마다 무엇을 채웠는지 기록하겠습니다. 실패한 노드는 "
                       "한 번 재시도한 뒤 기본값으로 넘어가도록 설계하겠습니다. 어, 그리고 어느 단계에서 실패했는지 로그로 남겨서 "
                       "나중에 같은 오류가 반복되는지 확인하겠습니다.",
        "duration_sec": 31.8, "timed_out": False,
        "delivery": {"measurable": True, "frontal_ratio": 0.79, "gaze_away_count": 2},
    },
}
QA = [{"question_id": q["question_id"], "type": q["type"], "text": q["text"], **ANSWERS[q["question_id"]]}
      for q in sorted(READY["questions"], key=lambda q: q["order"])]

# ------------------------------------------------------------------ 판정과 피드백 문구 (LLM 이 쓸 부분을 사람이 대신 씀)
# 판정은 C 의 원래 mock 과 같음: 직무 적합성 NEEDS_WORK (RQ-004 LangGraph), 답변 일관성 SUFFICIENT (CL-001)

ATTITUDE_ADVICE = [
    ("Q-2에서 「것 같습니다」로 흐리는 문장이 여러 번 나왔습니다. 직접 한 일은 「했습니다」로 끝맺어 보세요.",
     [("Q-2", "의견이 갈렸을 때는 각자 근거를 정리해서 다시 이야기했던 것 같습니다")]),
    ("Q-3에서 1분 30초를 넘겨 결과를 말하기 전에 답변이 끊겼습니다. 결론을 먼저 말하고 과정은 두세 문장으로 줄여 보세요.", []),
    ("「어」, 「음」 같은 군말은 문장을 시작할 때 주로 나왔습니다. 첫 문장을 미리 정해 두면 줄일 수 있습니다.",
     [("Q-2", "어 그러니까 음 팀에서 함께 했던 것 같습니다")]),
]
JOB_FIT = {
    "verdict": "NEEDS_WORK",
    "reason": "평가용 질문 50개와 상위 3개 적중 비율로 검색 정확도를 재고 개선한 과정은 직무기술서의 검색 정확도 측정, 개선 업무와 "
              "잘 맞습니다. 하지만 우대 사항인 LangGraph는 써 보지 못했다고 답했고, 여러 단계 LLM 흐름의 오류 처리는 재시도와 "
              "기본값이라는 방향만 제시했습니다.",
    "quotes": [("Q-4", "정확도는 평가용 질문 50개에 대해 정답 문서가 상위 3개 안에 들어오는 비율로 측정했습니다"),
               ("Q-4", "다만 LangGraph 같은 워크플로 도구는 써 보지 못했습니다"),
               ("Q-5", "실패한 노드는 한 번 재시도한 뒤 기본값으로 넘어가도록 설계하겠습니다")],
    "refs": ["RQ-004", "RQ-007", "RQ-006", "RQ-005"],
}
CONSISTENCY = {
    "verdict": "SUFFICIENT",
    "reason": "답변에서 말한 검색 정확도 20% 개선과 평가용 질문 50개 비교는 이력서 내용과 같습니다. LangGraph를 직접 써 보지 "
              "않았다는 답변도 이력서의 「학습 중」과 맞습니다. 서류와 어긋나는 내용은 없었습니다.",
    "quotes": [("Q-1", "RAG 검색 정확도를 20% 개선한 경험이 있습니다"), ("Q-4", "처음에는 50개 중 30개가 들어왔는데"),
               ("Q-5", "LangGraph는 직접 써 보지 않았지만")],
    "refs": ["CL-001", "CL-003", "CL-005"],
}
# linked_claim_ids = 질문에 연결된 확인 포인트의 claim + LLM 이 더한 claim(extra_claim_ids)
PER_QUESTION = {
    "Q-1": {"strengths": ["지원 직무와 맞는 RAG 경험을 20%라는 수치와 함께 먼저 꺼냈습니다.",
                          "평가용 질문 50개로 비교했다는 측정 방법까지 짧게 언급했습니다."],
            "gaps": ["팀에서 맡은 역할은 이름만 나오고 무엇을 했는지는 빠져 있습니다."],
            "next_action": "마지막 문장 앞에 팀에서 직접 결정한 일 하나를 넣어 보세요.",
            "linked_claim_ids": ["CL-001", "CL-003", "CL-006"], "linked_checkpoint_ids": ["CP-001"]},
    "Q-2": {"strengths": ["청크 크기를 두고 의견이 갈린 상황과 데이터로 결정했다는 결론이 나옵니다."],
            "gaps": ["누가 어떤 근거를 냈고 어떤 데이터로 비교했는지가 빠져 있습니다.",
                     "본인 역할이 회의 일정 정리에 그쳐 조율에서 한 일이 드러나지 않습니다."],
            "next_action": "상황, 본인이 낸 의견, 비교한 데이터, 결과 순서로 사례를 다시 정리해 보세요.",
            "linked_claim_ids": ["CL-002", "CL-004"], "linked_checkpoint_ids": ["CP-002"]},
    "Q-3": {"strengths": ["필수 기능 세 가지를 정하고 나머지를 미룬 우선순위 기준이 분명합니다.",
                          "매일 진행 상황을 공유하는 자리를 만들어 막힌 부분을 바로 나눈 점이 드러납니다."],
            "gaps": ["시간 제한으로 답변이 끊겨 결과와 배운 점을 말하지 못했습니다."],
            "next_action": "결과를 첫 문장에 말하고, 과정은 기준과 본인 역할 두 가지로 줄여 90초 안에 마무리해 보세요.",
            "linked_claim_ids": ["CL-002", "CL-004"], "linked_checkpoint_ids": ["CP-002"]},
    "Q-4": {"strengths": ["평가 데이터(질문 50개), 지표(상위 3개 적중 비율), 전후 값(30개에서 36개)을 모두 말했습니다.",
                          "청크 크기와 겹침을 어떻게 바꿨는지 구체적으로 설명했습니다."],
            "gaps": ["청크 조정과 리랭커 추가의 효과를 나눠 보지 않아 무엇이 개선을 이끌었는지 알기 어렵습니다."],
            "next_action": "두 변경을 따로 적용했을 때의 결과를 한 문장으로 말할 수 있게 준비해 두세요.",
            "linked_claim_ids": ["CL-001", "CL-003", "CL-005"], "linked_checkpoint_ids": ["CP-001"]},
    "Q-5": {"strengths": ["상태를 하나의 객체로 두고 단계마다 기록한다는 설계 방향을 설명했습니다.",
                          "실패 처리를 재시도, 기본값, 로그 세 단계로 나눠 말했습니다."],
            "gaps": ["직접 써 본 경험이 없어 실제 적용 사례가 없습니다."],
            "next_action": "작은 예제로 노드 두 개짜리 흐름을 직접 만들어 보고, 그 경험을 답변 첫 문장에 넣어 보세요.",
            "linked_claim_ids": ["CL-005"], "linked_checkpoint_ids": ["CP-003"]},
}
EDGE_QID = "Q-3"  # report_edge.json 에서 인식되지 않은 답변
NO_ANSWER_NEXT_ACTION = "답변이 기록되지 않았습니다. 마이크 연결을 확인하고 이 질문을 다시 연습해 보세요."

# ------------------------------------------------------------------ 조립


def find(answer: str, quote: str) -> tuple[int, int]:
    i = answer.find(quote)
    if i < 0:
        raise ValueError(f"인용이 답변에 없음: {quote}")
    return i, i + len(quote)


class QuoteIds:
    def __init__(self):
        self.n = 0

    def make(self, qa_by_id, qid, text):
        self.n += 1
        start, end = find(qa_by_id[qid]["answer_text"], text)
        return {"quote_id": f"QT-{self.n:03d}", "question_id": qid, "text": text, "start": start, "end": end}


def build(qa: list[dict], per_question: dict, job_fit: dict, consistency: dict, advice: list) -> dict:
    by_id = {q["question_id"]: q for q in qa}
    ids = QuoteIds()
    metrics = attitude_metrics(
        Answer(question_id=q["question_id"], transcript=q["answer_text"],
               transcript_status="DONE" if q["answer_text"] else "NO_SPEECH",
               duration_sec=q["duration_sec"], timed_out=q["timed_out"], delivery=q["delivery"])
        for q in qa)
    attitude_quotes, advice_text = [], []
    for text, quotes in advice:
        advice_text.append(text)
        attitude_quotes += [ids.make(by_id, qid, t) for qid, t in quotes]

    def fit(f):
        return {"verdict": f["verdict"], "reason": f["reason"],
                "quotes": [ids.make(by_id, qid, t) for qid, t in f["quotes"]], "refs": f["refs"]}

    jf, cs = fit(job_fit), fit(consistency)
    pq = [{"question_id": qid, **per_question[qid]} for qid in by_id]
    # 화면 7 이 다른 API 를 부르지 않도록 참조한 항목만 동봉 (러너와 같은 규칙)
    req_ids = set(jf["refs"])
    claim_ids = set(cs["refs"]) | {c for p in pq for c in p["linked_claim_ids"]}
    cp_ids = {c for p in pq for c in p["linked_checkpoint_ids"]}
    return {
        "session_id": SESSION_ID,
        "attitude": {"metrics": metrics, "advice": advice_text, "quotes": attitude_quotes},
        "job_fit": jf,
        "consistency": cs,
        "per_question": pq,
        "questions": [{"question_id": q["question_id"], "type": q["type"], "text": q["text"],
                       "answer_text": q["answer_text"]} for q in qa],
        "requirements": [{"requirement_id": r["requirement_id"], "text": r["text"], "kind": r["kind"]}
                         for r in sorted(REQUIREMENTS, key=lambda r: r["requirement_id"]) if r["requirement_id"] in req_ids],
        "claims": [{"claim_id": c["claim_id"], "text": c["text"]}
                   for c in sorted(CLAIMS, key=lambda c: c["claim_id"]) if c["claim_id"] in claim_ids],
        "checkpoints": [{"checkpoint_id": c["checkpoint_id"], "title": c["title"]}
                        for c in sorted(CHECKPOINTS, key=lambda c: c["checkpoint_id"]) if c["checkpoint_id"] in cp_ids],
    }


def build_edge() -> dict:
    """예외 상태: Q-3 답변 인식 안 됨(NO_SPEECH), 카메라 측정 불가, 답변 일관성 판단 보류."""
    qa = copy.deepcopy(QA)
    for q in qa:
        q["delivery"] = {"measurable": False, "frontal_ratio": None, "gaze_away_count": None}
    edge = next(q for q in qa if q["question_id"] == EDGE_QID)
    edge.update(answer_text=None, duration_sec=12.0, timed_out=False)
    pq = copy.deepcopy(PER_QUESTION)
    pq[EDGE_QID] = {**pq[EDGE_QID], "strengths": [], "gaps": [], "next_action": NO_ANSWER_NEXT_ACTION}  # 연결 정보는 유지
    consistency = {
        "verdict": "WITHHELD",
        "reason": "서류와 비교할 수 있는 근거 문장을 답변에서 찾지 못해 판단을 보류했습니다.",
        "quotes": [], "refs": [],
    }
    advice = [
        ("Q-2에서 「것 같습니다」로 흐리는 문장이 여러 번 나왔습니다. 직접 한 일은 「했습니다」로 끝맺어 보세요.", []),
        ("카메라 측정이 되지 않아 시선 지표는 표시하지 않습니다.", []),
    ]
    return build(qa, pq, JOB_FIT, consistency, advice)


# ------------------------------------------------------------------ 검사 (계약 규칙)


def check(report: dict, name: str) -> list[str]:
    errs = []
    answers = {q["question_id"]: q["answer_text"] for q in report["questions"]}
    rq = {r["requirement_id"] for r in report["requirements"]}
    cl = {c["claim_id"] for c in report["claims"]}
    cp = {c["checkpoint_id"] for c in report["checkpoints"]}
    all_quotes = report["attitude"]["quotes"] + report["job_fit"]["quotes"] + report["consistency"]["quotes"]
    qids = [q["quote_id"] for q in all_quotes]
    if len(qids) != len(set(qids)):
        errs.append("quote_id 중복")
    for q in all_quotes:  # T-201, T-202
        a = answers.get(q["question_id"])
        if a is None or a[q["start"]:q["end"]] != q["text"]:
            errs.append(f"{q['quote_id']} 인용이 답변 원문 위치와 다름")
        if not re.fullmatch(r"QT-\d{3}", q["quote_id"]):
            errs.append(f"{q['quote_id']} 형식")
    for area in ("job_fit", "consistency"):  # T-203
        f = report[area]
        for ref in f["refs"]:
            if ref not in rq | cl:
                errs.append(f"{area} refs 에 없는 ID {ref}")
        if f["verdict"] != "WITHHELD" and not f["quotes"]:
            errs.append(f"{area} 판정에 인용 없음")
    for p in report["per_question"]:
        errs += [f"{p['question_id']} 없는 claim {i}" for i in p["linked_claim_ids"] if i not in cl]
        errs += [f"{p['question_id']} 없는 checkpoint {i}" for i in p["linked_checkpoint_ids"] if i not in cp]
        cp_claims = [c for x in QUESTION_CPS[p["question_id"]] for c in next(k for k in CHECKPOINTS
                                                                             if k["checkpoint_id"] == x)["claim_ids"]]
        if p["linked_checkpoint_ids"] != QUESTION_CPS[p["question_id"]] or p["linked_claim_ids"][:len(cp_claims)] != cp_claims:
            errs.append(f"{p['question_id']} 연결 정보가 러너 규칙(확인 포인트의 claim 먼저)과 다름")
    if len(report["per_question"]) != 5 or len(report["attitude"]["metrics"]["time"]["per_question"]) != 5:
        errs.append("질문 5개가 아님")
    ready = [(q["question_id"], q["type"], q["text"]) for q in sorted(READY["questions"], key=lambda q: q["order"])]
    if [(q["question_id"], q["type"], q["text"]) for q in report["questions"]] != ready:
        errs.append("질문이 session_ready.json 과 다름")
    if "verdict" in report["attitude"] or "score" in json.dumps(report["attitude"]):  # T-214
        errs.append("태도에 판정이나 점수 있음")
    text = json.dumps({k: report[k] for k in ("attitude", "job_fit", "consistency", "per_question")}, ensure_ascii=False)
    if m := FORBIDDEN.search(text):  # T-013
        errs.append(f"금지 표현: {m.group(0)}")
    for c in CLAIMS:  # T-204 서류 원문 그대로
        if c["text"] not in DOC_TEXT[c["source_doc"]]:
            errs.append(f"{c['claim_id']} 서류 원문에 없음")
    for r in REQUIREMENTS:
        if r["text"] not in DOC_TEXT[r["source_doc"]]:
            errs.append(f"{r['requirement_id']} 원문에 없음")
    print(f"{name}: " + ("검사 통과" if not errs else f"문제 {len(errs)}개"))
    for e in errs:
        print("  -", e)
    return errs


def main():
    out = {"report.json": build(QA, PER_QUESTION, JOB_FIT, CONSISTENCY, ATTITUDE_ADVICE), "report_edge.json": build_edge()}
    failed = False
    for name, rep in out.items():
        failed |= bool(check(rep, name))
        (OUT / name).write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    m = out["report.json"]["attitude"]["metrics"]
    print(f"report.json 측정값: 분당 어절 {m['speech']['words_per_min']}, 군말 {m['speech']['filler_count']}회, "
          f"정면 유지 {m['gaze']['frontal_ratio']}, 이탈 {m['gaze']['gaze_away_count']}회, 시간 초과 {m['time']['timed_out_count']}회")
    for q in QA:
        n = len(q["answer_text"].split())
        print(f"  {q['question_id']}: {n}어절 / {q['duration_sec']}초 = 분당 {n / q['duration_sec'] * 60:.0f}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
