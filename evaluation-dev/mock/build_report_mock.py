"""report.json, report_edge.json 생성 스크립트 (담당 E, W-14).

인용 위치(start, end)를 코드로 계산하고, 태도 측정값은 evaluate/attitude.py 로 계산해 mock 에 넣고,
만든 뒤 계약 규칙으로 스스로 검사합니다. 답변이나 판정 문구를 고치려면 이 파일을 고친 뒤 다시 실행하세요.

    python build_report_mock.py            # report.json, report_edge.json 생성 + 검사

서류 원문 검사는 A 의 데모 서류(orchestration-dev/data/demo/*.txt)를 옆에 _*.txt 로 두었을 때만 합니다.
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from evaluate.attitude import attitude_metrics  # noqa: E402  측정값은 실제 계산 모듈로
from evaluate.contract import Answer  # noqa: E402
SESSION_ID = "S-3f2a9c1e"

# ------------------------------------------------------------------ 규칙 (9/29 C-D 테스트에서 정함)

FORBIDDEN = re.compile(r"합격|불합격|채용 점수|상위 ?\d+ ?%|자신감|진실성|거짓|긴장|불안")  # T-013


# ------------------------------------------------------------------ 분석 결과 (A 샘플 기준, ID 는 mock 용)
# claim 문장은 A 의 데모 서류 원문 그대로, 번호는 A 의 정답 라벨(C1~C11, CP1~CP7) 순서를 따름

REQUIREMENTS = [
    {"requirement_id": "RQ-003", "text": "RAG 또는 벡터 데이터베이스 활용 경험", "kind": "SKILL", "source_doc": "job_posting"},
    {"requirement_id": "RQ-005", "text": "LLM 응답 품질을 정량적으로 평가하고 모니터링한 경험", "kind": "SKILL", "source_doc": "job_posting"},
    {"requirement_id": "RQ-011", "text": "문제를 스스로 정의하고 근거를 바탕으로 해결하는 사람", "kind": "TALENT", "source_doc": "job_posting"},
    {"requirement_id": "RQ-014", "text": "검색 품질 평가 데이터셋 구축과 검색 지표(Recall@k 등) 측정", "kind": "DUTY", "source_doc": "job_description"},
]
CLAIMS = [
    {"claim_id": "CL-001", "text": "검색 정확도를 20% 개선했습니다", "source_doc": "cover_letter"},
    {"claim_id": "CL-002", "text": "검색 정확도 20% 개선", "source_doc": "resume"},
    {"claim_id": "CL-003", "text": "만개의레시피 데이터 1,000개를 크롤링·전처리해", "source_doc": "resume"},
    {"claim_id": "CL-004", "text": "약 5,000개의 레시피 데이터를 수집해", "source_doc": "cover_letter"},
    {"claim_id": "CL-006", "text": "프로젝트를 주도했습니다", "source_doc": "cover_letter"},
    {"claim_id": "CL-007", "text": "4인 팀, 팀 리드", "source_doc": "resume"},
    {"claim_id": "CL-010", "text": "Pydantic 스키마로 에이전트 간 데이터 형식을 먼저 합의하자고 제안했고", "source_doc": "cover_letter"},
]
CHECKPOINTS = [
    {"checkpoint_id": "CP-001", "title": "검색 정확도 측정 기준"},
    {"checkpoint_id": "CP-002", "title": "레시피 데이터 규모 불일치"},
    {"checkpoint_id": "CP-004", "title": "주도한 역할의 구체 내용"},
]

# ------------------------------------------------------------------ 질문과 답변 (섞인 결과 시나리오)
# 답변은 받아쓰기 결과처럼 군말을 남겼음. Q-5 는 1분 30초에서 끊김.

QA = [
    {
        "question_id": "Q-1", "type": "INTRO",
        "text": "간단히 자기소개를 부탁드립니다. 지원한 직무와 관련해 가장 자신 있는 경험을 중심으로 말씀해 주세요.",
        "answer_text": "안녕하세요. 저는 AI Agent 엔지니어로 지원한 김하늘입니다. 음, 교육과정에서 세 번의 팀 프로젝트를 했는데요, "
                       "가장 자신 있는 건 레시피 RAG 챗봇입니다. 전처리 규칙과 임베딩 문서 구성을 바꿔서 검색 정확도를 20% 개선했습니다. "
                       "어, 그리고 ProofLetter 프로젝트에서는 팀 리드를 맡아서 LangGraph로 멀티 에이전트 구조를 설계했습니다. "
                       "브라이트런에서 사내 문서 검색 품질을 높이는 일에 이 경험을 바로 쓰고 싶습니다.",
        "duration_sec": 34.6, "timed_out": False,
        "delivery": {"measurable": True, "frontal_ratio": 0.86, "gaze_away_count": 2},
    },
    {
        "question_id": "Q-2", "type": "BEHAVIOR",
        "text": "예상하지 못한 문제가 생겼을 때 원인을 스스로 정의하고 근거를 찾아 해결한 경험을 말씀해 주세요.",
        "answer_text": "레시피 챗봇에서 재료 이름이 조금만 달라도 엉뚱한 레시피가 나오는 문제가 있었습니다. 처음에는 모델 문제라고 생각했는데, "
                       "실패한 질문 서른 개를 모아서 보니까 대부분 재료 표기가 달라서 생긴 문제였습니다. 그래서 대파와 파처럼 같은 재료를 "
                       "하나로 묶는 전처리 규칙을 만들었고, 같은 질문 서른 개로 다시 확인해서 스물네 개가 제대로 나오는 걸 확인했습니다. "
                       "원인을 추측하지 않고 실패 사례부터 모아 보는 습관이 생겼습니다.",
        "duration_sec": 37.2, "timed_out": False,
        "delivery": {"measurable": True, "frontal_ratio": 0.81, "gaze_away_count": 3},
    },
    {
        "question_id": "Q-3", "type": "BEHAVIOR",
        "text": "팀원들과 작업 방식이 달라 문제가 생겼던 경험이 있다면, 어떻게 합의했고 본인은 어떤 역할을 했는지 말씀해 주세요.",
        "answer_text": "ProofLetter에서 팀원마다 에이전트 출력 형식이 달라서 통합이 자주 깨졌습니다. 어, 제가 Pydantic 스키마로 형식을 "
                       "먼저 맞추자고 제안했고요. 음, 팀원들이랑 회의해서 필드를 같이 정했습니다. 그 뒤로는 통합 오류가 많이 줄었던 것 같습니다. "
                       "어, 제가 팀 리드여서 전체적으로 조율하는 역할을 했던 것 같습니다.",
        "duration_sec": 26.8, "timed_out": False,
        "delivery": {"measurable": True, "frontal_ratio": 0.74, "gaze_away_count": 4},
    },
    {
        "question_id": "Q-4", "type": "TECH",
        "text": "이력서에 검색 정확도를 20% 개선했다고 쓰셨습니다. 정확도를 어떤 평가 데이터와 지표로 측정했는지, 그리고 임베딩 문서 구성을 "
                "바꾼 것이 검색 품질에 어떤 영향을 주었는지 설명해 주세요.",
        "answer_text": "어, 정확도는 저희가 만든 테스트 질문으로 확인했습니다. 크롤링한 레시피는 천 개 정도였고요, 임베딩할 때 레시피 제목만 "
                       "넣다가 재료랑 조리법까지 같이 넣었더니 검색 결과가 확실히 좋아졌습니다. 음, 정확한 지표 이름은 기억이 잘 안 나는데, "
                       "결과가 좋아진 걸 팀원들이랑 같이 확인했습니다.",
        "duration_sec": 24.9, "timed_out": False,
        "delivery": {"measurable": True, "frontal_ratio": 0.69, "gaze_away_count": 5},
    },
    {
        "question_id": "Q-5", "type": "TECH",
        "text": "LLM 응답 품질을 정량적으로 평가하고 운영 중에 모니터링하려면 어떻게 설계하시겠습니까? 직접 경험이 없다면 알고 있는 범위에서 "
                "설명해 주셔도 됩니다.",
        "answer_text": "LLM 응답 품질은 먼저 정답이 있는 질문 세트를 만들어서 답변이 정답 문서를 근거로 삼았는지 확인하는 게 좋을 것 같습니다. "
                       "어, 운영 중에는 사용자가 답변에 만족했는지 표시하게 하고, 로그를 모아서 자주 틀리는 질문을 따로 보겠습니다. "
                       "음, 직접 해 본 건 아니지만 LLM을 평가자로 쓰는 방법도 있는데, 평가자도 틀릴 수 있어서 사람이 일부를 다시 확인해야 "
                       "한다고 생각합니다. 평가 항목은 근거 문서를 제대로 찾았는지, 답변 내용이 그 문서와 맞는지, 질문에 필요한 내용을 빠뜨리지 "
                       "않았는지 이렇게 세 가지로 나눠서 보면 좋을 것 같습니다. 어, 검색 단계는 정답 문서가 상위 몇 개 안에 들어오는지로 보고, "
                       "생성 단계는 답변 문장이 근거 문서에 실제로 있는 내용인지를 확인하는 식으로 나누면 어디서 틀렸는지 알 수 있습니다. "
                       "음, 모니터링은 매일 정해진 질문 세트를 자동으로 돌려서 점수가 떨어지면 알림을 받게 하고, 새 문서가 들어오거나 "
                       "프롬프트를 바꿨을 때는 꼭 다시 돌려 보겠습니다. 그리고 저기 비용이랑 응답 시간도 같이 봐야 하는데, 어",
        "duration_sec": 90.0, "timed_out": True,
        "delivery": {"measurable": True, "frontal_ratio": 0.78, "gaze_away_count": 3},
    },
]

# ------------------------------------------------------------------ 판정과 피드백 문구 (LLM 이 쓸 부분을 사람이 대신 씀)

ATTITUDE_ADVICE = [
    ("문장 끝을 「것 같습니다」로 흐리는 표현이 자주 나왔습니다. 직접 한 일은 「했습니다」로 끝맺어 보세요.",
     [("Q-3", "그 뒤로는 통합 오류가 많이 줄었던 것 같습니다")]),
    ("Q-5에서 1분 30초를 넘겨 답변이 중간에 끊겼습니다. 결론을 먼저 말하고 근거를 두세 개 붙이는 순서로 줄여 보세요.", []),
    ("「어」, 「음」 같은 군말은 주로 문장을 시작할 때 나왔습니다. 첫 문장을 미리 정해 두고 시작하면 줄일 수 있습니다.", []),
]
JOB_FIT = {
    "verdict": "NEEDS_WORK",
    "reason": "RAG 검색 시스템을 만들고 검색 품질을 개선한 경험은 구체적으로 설명했습니다. 하지만 직무기술서가 요구하는 검색 지표"
              "(Recall@k 등) 측정 방법은 답하지 못했고, 자격 요건인 LLM 응답 품질 평가는 직접 경험 없이 방향만 설명했습니다.",
    "quotes": [("Q-4", "정확한 지표 이름은 기억이 잘 안 나는데"), ("Q-5", "직접 해 본 건 아니지만 LLM을 평가자로 쓰는 방법도 있는데")],
    "refs": ["RQ-014", "RQ-005", "RQ-003"],
}
CONSISTENCY = {
    "verdict": "NEEDS_WORK",
    "reason": "자기소개서에는 레시피 데이터를 약 5,000개 수집했다고 썼지만, 답변에서는 천 개 정도라고 말했습니다. 이력서의 1,000개와는 "
              "맞으니 자기소개서 수치를 확인해 두세요. 검색 정확도 20% 개선과 Pydantic 스키마 제안은 서류와 일치합니다.",
    "quotes": [("Q-4", "크롤링한 레시피는 천 개 정도였고요"), ("Q-1", "검색 정확도를 20% 개선했습니다"),
               ("Q-3", "제가 Pydantic 스키마로 형식을 먼저 맞추자고 제안했고요")],
    "refs": ["CL-004", "CL-003", "CL-001", "CL-010"],
}
PER_QUESTION = {
    "Q-1": {"strengths": ["지원 직무와 연결된 RAG 경험을 수치(20%)와 함께 먼저 꺼냈습니다.",
                          "마지막에 회사의 사내 문서 검색 사업과 경험을 연결했습니다."],
            "gaps": ["20%가 무엇을 기준으로 한 수치인지 한 마디가 빠져 있어 바로 추가 질문을 받게 됩니다."],
            "next_action": "「테스트 질문 몇 개 중 몇 개가 정답 문서를 찾았다」처럼 20%의 기준을 한 문장으로 붙여 보세요.",
            "linked_claim_ids": ["CL-001", "CL-002"], "linked_checkpoint_ids": ["CP-001"]},
    "Q-2": {"strengths": ["실패한 질문 서른 개를 모아 원인을 확인한 과정이 드러납니다.",
                          "해결 후 같은 질문으로 다시 확인해 결과(서른 개 중 스물네 개)를 수치로 말했습니다."],
            "gaps": ["남은 여섯 개가 왜 실패했는지, 그다음에 무엇을 했는지는 빠져 있습니다."],
            "next_action": "해결하지 못한 부분과 다음 조치를 한 문장으로 덧붙이면 문제를 끝까지 다룬 인상이 강해집니다.",
            "linked_claim_ids": [], "linked_checkpoint_ids": []},
    "Q-3": {"strengths": ["문제(출력 형식 불일치)와 본인 제안(Pydantic 스키마)이 분명합니다."],
            "gaps": ["팀 리드로서 직접 내린 결정이 무엇이었는지 드러나지 않습니다.",
                     "「통합 오류가 많이 줄었다」의 근거가 없습니다."],
            "next_action": "리드로서 결정한 것 하나(예: 필드 목록 확정, 병합 순서)와 오류가 얼마나 줄었는지를 구체적으로 말해 보세요.",
            "linked_claim_ids": ["CL-006", "CL-007", "CL-010"], "linked_checkpoint_ids": ["CP-004"]},
    "Q-4": {"strengths": ["임베딩 문서에 재료와 조리법을 함께 넣은 변경 내용을 설명했습니다."],
            "gaps": ["평가 데이터의 규모와 지표 이름, 개선 전후 값을 말하지 못했습니다.",
                     "데이터 규모(천 개 정도)가 자기소개서의 약 5,000개와 다릅니다."],
            "next_action": "평가 질문 수, 지표(예: 상위 k개 안에 정답이 든 비율), 전후 값을 한 문장으로 정리해 두고, 서류의 데이터 규모를 하나로 맞추세요.",
            "linked_claim_ids": ["CL-001", "CL-002", "CL-003", "CL-004"], "linked_checkpoint_ids": ["CP-001", "CP-002"]},
    "Q-5": {"strengths": ["정답 세트 기반 평가, 운영 로그, LLM 평가자의 한계까지 방향을 폭넓게 짚었습니다."],
            "gaps": ["직접 해 본 경험이 없어 구체적인 지표나 기준값이 없습니다.", "시간 안에 결론까지 말하지 못했습니다."],
            "next_action": "교육과정 프로젝트에서 평가를 해 본 사례가 있다면 그 경험을 먼저 말하고, 없으면 지표 하나와 기준값을 정해 짧게 답해 보세요.",
            "linked_claim_ids": [], "linked_checkpoint_ids": []},
}

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

    return {
        "session_id": SESSION_ID,
        "attitude": {"metrics": metrics, "advice": advice_text, "quotes": attitude_quotes},
        "job_fit": fit(job_fit),
        "consistency": fit(consistency),
        "per_question": [{"question_id": qid, **per_question[qid]} for qid in by_id],
        "questions": [{"question_id": q["question_id"], "type": q["type"], "text": q["text"],
                       "answer_text": q["answer_text"]} for q in qa],
        "requirements": [{"requirement_id": r["requirement_id"], "text": r["text"], "kind": r["kind"]}
                         for r in REQUIREMENTS],  # (제안) refs 의 RQ- 문구를 화면에 그리기 위해 동봉
        "claims": [{"claim_id": c["claim_id"], "text": c["text"]} for c in CLAIMS],
        "checkpoints": CHECKPOINTS,
    }


def build_edge() -> dict:
    """예외 상태: Q-3 답변 인식 안 됨, 카메라 측정 불가, 답변 일관성 판단 보류."""
    qa = copy.deepcopy(QA)
    for q in qa:
        q["delivery"] = {"measurable": False, "frontal_ratio": None, "gaze_away_count": None}
    q3 = next(q for q in qa if q["question_id"] == "Q-3")
    q3["answer_text"] = None
    q3["duration_sec"] = 12.0
    pq = copy.deepcopy(PER_QUESTION)
    pq["Q-3"] = {"strengths": [], "gaps": [],
                 "next_action": "답변이 기록되지 않았습니다. 마이크 연결을 확인하고 이 질문을 다시 연습해 보세요.",
                 "linked_claim_ids": ["CL-006", "CL-007", "CL-010"], "linked_checkpoint_ids": ["CP-004"]}
    consistency = {
        "verdict": "WITHHELD",
        "reason": "서류와 비교할 수 있는 근거 문장을 답변에서 찾지 못해 판단을 보류했습니다.",
        "quotes": [], "refs": [],
    }
    advice = [
        ("Q-5에서 1분 30초를 넘겨 답변이 중간에 끊겼습니다. 결론을 먼저 말하고 근거를 두세 개 붙이는 순서로 줄여 보세요.", []),
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
        if f["verdict"] == "SUFFICIENT" and not f["quotes"]:
            errs.append(f"{area} SUFFICIENT 인데 인용 없음")
        if f["verdict"] != "WITHHELD" and not f["quotes"]:
            errs.append(f"{area} 판정에 인용 없음")
    for p in report["per_question"]:
        errs += [f"{p['question_id']} 없는 claim {i}" for i in p["linked_claim_ids"] if i not in cl]
        errs += [f"{p['question_id']} 없는 checkpoint {i}" for i in p["linked_checkpoint_ids"] if i not in cp]
    if len(report["per_question"]) != 5 or len(report["attitude"]["metrics"]["time"]["per_question"]) != 5:
        errs.append("질문 5개가 아님")
    if "verdict" in report["attitude"] or "score" in json.dumps(report["attitude"]):  # T-214
        errs.append("태도에 판정이나 점수 있음")
    text = json.dumps({k: report[k] for k in ("attitude", "job_fit", "consistency", "per_question")}, ensure_ascii=False)
    if m := FORBIDDEN.search(text):  # T-013
        errs.append(f"금지 표현: {m.group(0)}")
    docs = {p.stem.lstrip("_"): p.read_text(encoding="utf-8") for p in HERE.glob("_*.txt")}
    if docs:  # T-204 (A 서류가 있을 때만)
        for c in CLAIMS:
            if c["text"] not in docs[c["source_doc"]]:
                errs.append(f"{c['claim_id']} 서류 원문에 없음")
        for r in REQUIREMENTS:
            if r["text"] not in docs[r["source_doc"]]:
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
        (HERE / name).write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    m = out["report.json"]["attitude"]["metrics"]
    print(f"report.json 측정값: 분당 어절 {m['speech']['words_per_min']}, 군말 {m['speech']['filler_count']}회, "
          f"정면 유지 {m['gaze']['frontal_ratio']}, 이탈 {m['gaze']['gaze_away_count']}회, 시간 초과 {m['time']['timed_out_count']}회")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
