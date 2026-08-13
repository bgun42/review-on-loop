# agent-work-review

[English README](./README.md)

AI 에이전트가 작성한 코드 변경분을 **커밋/머지 전에** 검토하는 Claude Code 스킬입니다.
에이전트는 그럴듯한 코드를 빠르게 쓰지만, 실수의 유형이 예측 가능합니다. 이 스킬은
바로 그 유형을 겨냥한 5단계 리뷰를 수행합니다.

| 패스 | 잡아내는 것 |
|---|---|
| **회귀** | 호출처가 갱신되지 않은 심볼 변경/리네임, 직렬화 계약 파손, 몰래 수정된 테스트 단언 |
| **성능** | N+1 쿼리, 루프 내 I/O, sync-over-async, 무제한 읽기, 페이지네이션 누락 |
| **비용** | 트래픽·데이터 증가에 비례해 커지는 과금 — Cosmos DB / DynamoDB RU, 호출당 과금 API(LLM·SMS·지도), egress, 로그 수집량. Cosmos DB RU 딥다이브(cross-partition fan-out, 쿼리 vs point-read, 쓰기 증폭) 포함 |
| **가독성** | 나레이션 주석, 방어적 try/catch 남발, 사변적 일반화, 죽은 코드 — 에이전트 코드 특유의 냄새 |
| **컨벤션** | *당신 저장소의* 확립된 패턴과의 괴리 — 기준은 일반론이 아니라 당신 repo의 `CLAUDE.md`·린터 설정·이웃 파일에서 발견합니다 |

모든 발견 사항은 보고 전에 실제 코드로 재검증되며(**Confirmed** / **Needs
verification** 구분), Blocker / Major / Minor / Nit로 등급화되어 최종 판정(Approve ·
Approve with nits · Needs changes · Block)으로 집계됩니다.

## 설치

```
/plugin marketplace add <owner>/agent-work-review
/plugin install agent-work-review@agent-work-review
```

별도 설정은 없습니다. 컨벤션 기준은 리뷰 시점에 대상 저장소에서 학습합니다.

## 사용

다음과 같은 요청에 자동으로 발동합니다:

- "에이전트가 작업한 결과물 리뷰해줘"
- "커밋 전에 이 diff 검토해줘"
- "이 브랜치 머지해도 안전해?"
- "review what the agent just did"

리뷰 대상은 우선순위대로: 명시한 대상(PR·커밋 범위·경로) → 미커밋 작업 트리 변경 →
현재 브랜치와 기본 브랜치의 merge base 비교. 리포트는 대화 중인 언어로 작성됩니다.

## 구조

```
skills/agent-work-review/
├── SKILL.md                  # 5-pass 워크플로 본체
└── references/
    ├── regression.md         # 소비자 추적, 직렬화 경계
    ├── performance.md        # N+1, 무제한 읽기, sync-over-async
    ├── cost.md               # 과금 모델 + Cosmos DB 딥다이브
    ├── readability.md        # 에이전트 특유의 코드 냄새
    └── conventions.md        # repo 선례 발견·대조 방법
```

## 라이선스

MIT
