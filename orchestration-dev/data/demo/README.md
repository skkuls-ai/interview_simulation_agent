# 데모 샘플과 mock (담당 A)

고정 데모 시나리오: 가상 지원자 "김하늘"의 서류 4종. 「RAG 검색 정확도를 20% 개선」 주장이 이력서와 자소서에 모두 있고, Q-1(자기소개)·Q-4(기술)와 연결됩니다 (docs/01, docs/07).

| 파일 | 용도 | docs 작업 | 최종 위치 |
|---|---|---|---|
| `resume.txt`, `job_posting.txt`, `job_description.txt`, `cover_letter.txt` | 사람이 읽고 고치는 원본 서류 4종 | - | 이 폴더 |
| `sample_inputs.json` | 서류 4종을 API 입력 필드 이름(`*_text`)으로 묶은 것. txt 에서 생성 | W-05 | `shared/mock/sample_inputs.json` |
| `session_preparing.json` | `GET /api/interviews/{id}` 응답 예시 (`PREPARING`, 2단계 완료·3단계 진행 중) | W-06 | `shared/mock/session_preparing.json` |
| `expected_points.json` | 서류 분석 정답 라벨 (주장 11, 검증 포인트 7, 요구사항 공백 4, 인재상 3, 함정 2) | 담당 A 채점용 | 이 폴더 |

- C의 저장소 뼈대(W-02)가 올라오면 `sample_inputs.json`, `session_preparing.json`을 `shared/mock/`으로 옮겨 PR을 보냅니다. `shared/mock/` 변경은 C 리뷰 후 머지합니다 (docs/07).
- txt 를 고치면 `sample_inputs.json`도 다시 만들어야 합니다. `tests/test_prep_demo_samples.py`가 두 파일이 같은지 검사합니다.
- 모든 서류는 가상 인물의 데모용이며 개인정보가 없습니다.

## 확인 필요 (A ↔ C)

- 화면 3의 2단계 완료 문구는 「경험 n개, 확인할 주장 n개」인데, docs/04 `Analysis`에는 경험(Experience) 항목이 없고 주장(Claim)만 있습니다. **"경험 n개"를 무엇으로 셀지** 정해야 합니다. (제안) 주장을 가진 프로젝트·활동 수를 분석 단계에서 코드로 세어 `detail` 문자열만 만듭니다.
- 1단계 「채용공고 읽는 중」은 채용공고와 직무기술서를 함께 분석하므로 `detail`의 요구사항 수는 두 문서 합계로 했습니다 (예시: 30개 = 채용공고 16 + 직무기술서 14).
