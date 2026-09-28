# STEP 0. 환경 준비와 기준선 확인

> 담당: 담당 1 (분석 에이전트 LLM 구현)
> 브랜치: `feature/interview-prep` (기반: `feature/orchestration`)

## 내 작업 범위

담당 3의 분석 그래프(`backend/interview/analysis_graph.py`)는 이미 완성되어 있고, 그래프가 호출하는 **분석 에이전트 8개가 스텁(키워드 규칙)** 상태입니다. 내 작업은 `AnalysisAgents` 인터페이스(`backend/interview/agents.py`)를 그대로 지키면서 LLM 구현으로 교체하는 것입니다.

```text
START ─┬→ analyze_jd ──────────┬→ link → find_verification_points → plan_questions
       └→ analyze_experiences ─┘                                         ↓
                                  validate_questions (검증 최대 3번, 재개인화 최대 2번 → 원본 문구로 되돌림)
                                         → build_rubric → assemble → InterviewBlueprint
```

| 메서드 | 그래프 노드 | 출력 |
|---|---|---|
| `analyze_jd` | analyze_jd | `CompanyContext`, `list[JDRequirement]` |
| `analyze_experiences` | analyze_experiences | `list[Experience]` |
| `link` | link | `list[RequirementLink]` |
| `verification_points` | find_verification_points | `list[VerificationPoint]` |
| `personalize` | plan_questions | `PlannedQuestion` (개인화 문구) |
| `validate_question` | validate_questions | `QuestionValidation` |
| `question_rubric` | build_rubric | `QuestionRubric` |
| `intro_rubric` | build_rubric | `IntroRubric` |

**그래프가 코드로 이미 처리하는 것:** 검증 포인트 ID 재부여(`V1`, `V2`…), 잘못된 영역 코드 보정, 질문 선정(역량 점수 순위), 검증 포인트의 질문 배정, 재개인화 횟수 제한

**연결 위치:** `backend/api/main.py`의 `build_service()`에서 `StubAnalysisAgents()` 대신 `LLMAnalysisAgents`를 주입합니다 (`# TODO: LLM 버전으로 교체`).

## 작업 원칙

- `AnalysisAgents` 인터페이스와 `InterviewBlueprint` 스키마는 **수정하지 않습니다.** 스키마 변경은 담당 3과 합의 후 진행합니다.
- LLM 출력의 ID와 원문 인용은 **코드로 검증**합니다.
- 단위 테스트는 **가짜 `JsonLLM`**을 주입해 API 없이 실행합니다. 실제 모델 호출은 별도 smoke test로 분리합니다.
- LLM 호출이 실패하면 스텁 결과로 대체(fallback)해서 그래프가 멈추지 않게 합니다.

## 환경

```bash
cd orchestration-dev
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
INTERVIEW_USE_LLM=0 .venv/bin/python -m pytest -q tests -p no:warnings
```

- 결과: **79 passed**
- 설치 버전: langgraph 1.2.12, google-genai 2.25.0, pydantic 2.13.5, fastapi 0.141.1

## Git 참고

- `feature/orchestration`은 `dev`와 **공통 조상이 없는 독립 커밋**입니다. 이 브랜치는 orchestration에서 땄기 때문에, 통합 담당자가 orchestration을 `dev`에 먼저 병합(최초 1회 `--allow-unrelated-histories`)한 뒤 일반 병합으로 합류합니다.

## 기준선: 스텁 분석 결과

테스트용 샘플(`tests/conftest.py`의 인사 직무 JD·이력서)로 분석 그래프를 실행한 결과입니다.

| 항목 | 스텁 결과 | 한계 |
|---|---|---|
| 요구사항 | 공고 줄마다 1개 (4개), 앞 3줄은 must | 줄 순서로 중요도를 정함 |
| 경험 | 이력서 줄마다 1개 (3개) | 성과(`claimed_results`) 없음 |
| 연결 | 키워드 겹침으로 strong/gap | 의미 연결 없음 |
| 검증 포인트 | "서류상 직무 적합성 주장" 2개 (JD 공백만) | **서류 속 주장(수치·역할·성과)을 검증하는 포인트가 없음** |
| 개인화 질문 | 0개 (원본 문항 그대로) | 개인화 없음 |
| 예상 시간 | 30~55분 | 기본 설정(4개 영역 × 2문항) 기준 |

이 결과를 LLM 구현 후 결과와 비교합니다. 발표에서 "스텁 대비 개선"을 보여주는 근거로 사용합니다.

## 다음 STEP

- STEP 1: 데모 샘플(공고·이력서·자소서)과 검증 포인트 정답 라벨 작성
- LLM 호출이 필요한 STEP 2부터는 `orchestration-dev/.env`에 Gemini 연결 정보가 필요합니다.
