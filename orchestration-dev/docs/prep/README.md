# 분석 에이전트 진행 현황 (담당 1)

> 브랜치: `feature/interview-prep` (기반: 담당 3의 `feature/orchestration`)
> 마지막 업데이트: 2026-09-28 밤

## docs WBS 기준 담당 A 작업 (9/29~)

| ID | 작업 | 마감 | 상태 |
|---|---|---|---|
| W-05 | `sample_inputs.json` (고정 데모 서류 4종) | 화 밤 | ✅ `data/demo/sample_inputs.json` |
| W-06 | `session_preparing.json` | 화 밤 | ✅ `data/demo/session_preparing.json` |
| W-06 | 분석 프롬프트 초안 (새 계약 `Analysis` 기준) | 화 밤 | ✅ `backend/proof_prep/prompts.py` |
| W-07 | 화면 1 시작, 화면 2 서류 업로드 (mock) | 화 밤 | ☐ C의 뼈대(W-02, W-11) 대기 |
| W-15 | 샘플 4종으로 `Analysis` 실제 생성 | 수 저녁 | ✅ 주장 11/11, 검증 포인트 6/7, 요구사항 공백 4/4, 20.4초 → [03 문서](03_W06_W15_새계약_서류분석.md) |
| W-16 | 화면 1·2 → `POST /api/interviews` 연결 | 수 저녁 | ☐ |
| W-28 | PDF·DOCX 추출, 입력 예외 처리 | 목 14시 | ☐ |

mock 파일은 C의 저장소 뼈대가 올라오면 `shared/mock/`으로 옮깁니다. 자세한 내용은 [`data/demo/README.md`](../../data/demo/README.md).

## 한눈에 보기 (STEP 기록)

| STEP | 내용 | 상태 | 문서 |
|---|---|---|---|
| 0 | 환경 준비, 작업 범위 확인, 스텁 기준선 측정 | ✅ 완료 | [00_STEP0_환경_기준선.md](00_STEP0_환경_기준선.md) |
| 1 | 데모 샘플과 정답 라벨 (**9/29 docs 기준 v2로 수정:** 서류 4종, 20% 시나리오, `sample_inputs.json`) | ✅ 완료 | [01_STEP1_데모_샘플.md](01_STEP1_데모_샘플.md) |
| 2 | `analyze_jd`, `analyze_experiences` LLM 구현 | ✅ 완료 | [02_STEP2_JD_경험_분석.md](02_STEP2_JD_경험_분석.md) |
| 3 | `link`, `verification_points` LLM 구현 | ⏳ 다음 | |
| 4 | `personalize`, `validate_question` LLM 구현 | ☐ (담당 5와 범위 정리 필요) | |
| 5 | `question_rubric`, `intro_rubric` LLM 구현 | ☐ | |
| 6 | `build_service()`에 연결, 준비 시간 측정, 평가 스크립트 | ☐ (담당 3과 함께) | |

**일정 목표:** STEP 2~3은 9/29, STEP 4~6은 9/30 오전, **9/30 저녁 1차 통합**

---

## 내 작업 범위

담당 3이 분석 그래프(`backend/interview/analysis_graph.py`)와 출력 스키마(`InterviewBlueprint`)를 이미 만들어 두었습니다. 그래프가 호출하는 **분석 에이전트 8개가 스텁(키워드 규칙)** 상태이고, 내 작업은 이것을 LLM으로 구현하는 것입니다.

```text
START ─┬→ analyze_jd ──────────┬→ link → find_verification_points → plan_questions
       └→ analyze_experiences ─┘                                         ↓
                                  validate_questions (검증 최대 3번, 재개인화 최대 2번 → 원본 문구로 되돌림)
                                         → build_rubric → assemble → InterviewBlueprint
```

- 구현 파일: `backend/interview/llm_analysis_agents.py` (신규)
- 연결 위치: `backend/api/main.py`의 `build_service()` (`# TODO: LLM 버전으로 교체`)

## 작업 원칙

- `AnalysisAgents` 인터페이스와 `InterviewBlueprint` 스키마는 **수정하지 않습니다.** 필드 추가는 담당 3과 합의 후 진행합니다.
- LLM 출력의 ID와 원문 인용은 **코드로 검증**합니다.
- 단위 테스트는 **가짜 LLM(`FakeLLM`)**으로 API 없이 실행합니다. 실제 모델 호출은 별도 smoke test로 분리합니다.
- LLM 호출이 실패하면 스텁 결과로 대체해서 그래프가 멈추지 않게 합니다.
- 질문 수, 면접 진행, 평가 코드, 다른 담당자 코드는 건드리지 않습니다.

---

## 완료한 작업

### STEP 0. 환경과 기준선

- 담당 3의 브랜치에서 `feature/interview-prep`를 만들고 가상환경(`orchestration-dev/.venv`, Python 3.12)을 구성했습니다.
- 기존 테스트 **79개 전부 통과**를 확인했습니다.
- 스텁으로 분석 그래프를 끝까지 실행해 **기준선**을 기록했습니다. 검증 포인트가 JD 공백만 잡히고, 개인화 질문은 0개입니다.

### STEP 1. 데모 샘플과 정답 라벨

- 가상 회사 공고, 가상 지원자 "김하늘"의 이력서와 자소서를 만들었습니다.
  - 이력서: 교육과정 팀 프로젝트(P04~06)를 바탕으로 **사실대로** 작성
  - 자소서: **확인이 필요한 주장을 일부러 심음**
- 정답 라벨 9개(L1~L9)와 오탐 함정 2개(N1, N2)를 **결과를 보기 전에** 확정했습니다.
- 라벨 인용이 원문에 정확히 한 번 있는지 확인하는 테스트 26개를 추가했습니다.
- **스텁 기준선: 정답 라벨 0/9 탐지.** 제목 줄("[데모용 가상 채용공고]", "담당 업무")을 요구사항으로 착각합니다.

| 파일 | 역할 |
|---|---|
| `data/demo/jd.txt`, `resume.txt`, `cover_letter.txt` | 테스트·실험·시연용 입력 (문제지) |
| `data/demo/expected_points.json` | 찾아야 할 검증 포인트와 함정 (정답지) |
| `tests/test_prep_demo_samples.py` | 정답지의 인용이 문제지에 실제로 있는지 검사 |

### 커밋

| 커밋 | 내용 |
|---|---|
| `70f23a1` | docs: 분석 에이전트 STEP 0 환경과 기준선 정리 |
| `f9307c9` | test: 분석 에이전트 데모 샘플과 검증 포인트 정답 라벨 추가 |

GitHub `feature/interview-prep`에 push 완료. 전체 테스트 **105개 통과** (기존 79 + 샘플 검사 26).

---

### STEP 2. JD 분석과 경험 분석 LLM 구현

- `quotes.py`(원문 인용 검증), `prompts/analysis.py`(출력 모델·프롬프트), `llm_analysis_agents.py`(`LLMAnalysisAgents`)를 만들었습니다.
- 구현한 메서드는 `analyze_jd`, `analyze_experiences` 두 개이고, 나머지 6개는 스텁을 상속합니다.
- **코드 안전장치:** 원문에 없는 요구사항·경험·주장 구절 제거, 없는 역량 코드 제거, ID는 코드가 부여, 실패하면 스텁으로 대체
- **서류별 경험 추출**과 **원문 그대로의 주장 구절 저장**으로, STEP 3이 서류 간 불일치와 주장을 근거로 검증 포인트를 만들 수 있게 했습니다.
- **실제 Gemini 결과 (데모 샘플):** 요구사항 16개(제목 줄 0개, 필수/우대 정확), 경험 7개, **정답 라벨의 서류 인용 7/7 포착** (스텁 0/7), 두 분석 동시 실행 약 10~15초
- smoke test 3회로 요구사항 상한, 괄호 잘림, 짧은 인용 거부 문제를 찾아 고쳤습니다.
- 테스트 **124개 통과** (인용 검증 8, LLM 분석 11 추가)

---

## 다음 작업: STEP 3

| 순서 | 작업 |
|---|---|
| 3-1 | `link`: 요구사항 ↔ 경험 연결 (strong / partial / gap)과 근거 |
| 3-2 | `verification_points`: 서류 속 주장 중 면접에서 확인할 것 (수치, 역할, 기술, 성과, 결정, 서류 간 불일치, JD 공백) |
| 3-3 | 코드 안전장치: 근거 구절은 STEP 2에서 검증된 `claimed_results` 안에서만 인정, 없는 요구사항·경험 ID 제거 |
| 3-4 | 정답 라벨 채점 스크립트: 탐지율(L1~L9), 오탐(N1, N2) |

**목표:** 정답 라벨 탐지, 함정 N1(이력서 "4인 팀" ↔ 자소서 "3명의 팀원과 함께")을 불일치로 잡지 않기

---

## 준비가 필요한 것

- [x] `orchestration-dev/.env`에 `GEMINI_API_KEY` 설정 (`.env.example`은 담당 3의 공용 파일이라 그대로 유지)
- [ ] VS Code 인터프리터를 `orchestration-dev/.venv/bin/python`으로 선택 (담당 3 설정은 Windows 경로)

## 팀 확인 필요 (9/29 아침)

자세한 내용은 `miniproject01/팀_논의사항_0929.md`에 정리했습니다. 이 파일은 저장소 밖에 있습니다.

- 분석 에이전트 LLM 구현을 담당 1이 맡는다는 것 (담당 3)
- 스키마에 원문 인용 필드 추가 제안 (담당 3)
- `validate_question` 담당 정리 (담당 5)
- 합불 판정 표시, 비언어 점수, 기술 질문 추가 방식, 데모 설정 등 제품 방향 결정 (전체)
- `main`에 perception 브랜치가 바로 병합됐다가 되돌려진 기록 → 기능 브랜치는 `dev`로만 PR

## 실행 명령

```bash
cd orchestration-dev
INTERVIEW_USE_LLM=0 .venv/bin/python -m pytest -q tests -p no:warnings   # 전체 테스트
.venv/bin/python -m pytest -q tests/test_prep_demo_samples.py -p no:warnings   # 샘플 검사만
```
