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
verification** 구분), CI 스타일로 분류됩니다: **Failed**(랜딩 전 필수 수정) /
**Warning**(권고, 차단 안 함) → 최종 판정 **Pass · Pass with warnings · Fail**.
문제없이 통과한 검사 항목은 명시적으로 Pass로 안내되고, 수정이 완료된 발견도
**Pass**로 보고됩니다.

## 설치

```
/plugin marketplace add bgun42/review-on-loop
/plugin install agent-work-review@review-on-loop
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

리뷰는 **명세 기반**입니다: 변경이 구현하는 명세서(요구사항·설계 문서, 수용 기준이
있는 티켓, API 계약)를 먼저 확인하고 그것을 기준으로 판정합니다. 명세가 없으면
리뷰하지 않고 번들된 `draft-spec` 스킬(`/draft`로 직접 호출 가능)이 먼저 나섭니다 — 대상 코드베이스(하우스룰·
컨벤션·워크플로·목표가 건드리는 코드)를 분석하고, 그 현실에 비추어 사용자의 목표를
해석한 뒤, 실행형 수용 기준을 갖춘 명세 초안을 작성해 사용자 확정을 받습니다.
확정 전에는 독립 guess-hunt 리뷰어가 초안을 감사해, 사용자에게 근거를 두지 않고
가정으로 확정된 결정을 찾아 되묻습니다.

## 루프 엔지니어링: `/work`

목표 기반 develop → review → fix 루프도 함께 제공합니다:

```
/work docs/fleet-fuel-spec.md 기준: 함대 연료합계 엔드포인트가 하우스룰을 지키며 동작; 기존 데이터·호출처 안 깨짐
```

권장 흐름: **`/init`**(repo당 1회) → **`/draft`**(명세 확정) → **`/work`**(그 명세를
인용한 루프).

- 루프는 **명시적 목표 없이는 시작하지 않습니다** — 목표와 검증 가능한 수용 기준을
  먼저 전달하며, 없으면 물어봅니다.
- **명세서 없이도 시작하지 않습니다** — 목표 계약은 작업이 구현하는 명세서를
  인용해야 하며, 없으면 `draft-spec` 스킬로 넘겨 명세를 먼저 작성하고 사용자가
  확정한 후에만 루프를 시작합니다.
- 매 반복: 개발(이미 diff가 있으면 생략) → 신선한 컨텍스트 리뷰(`agent-work-review`)
  → 정지 조건 체크 → 수정(`apply-review-findings`).
- **목표의 수용 기준이 검증되고 리뷰 판정이 Pass일 때 중지합니다.** 안전장치:
  최대 3회 반복, 발견이 줄지 않으면(진동) 사용자 에스컬레이션. Warning만으로는
  루프가 돌지 않습니다.
- **실행형 수용 기준**: 각 기준에 루프가 실제로 돌릴 체크(테스트 명령·grep 단언)를
  짝지어 종료 판정에서 모델 재량을 제거합니다. **발견 원장**
  (`.agent-review/ledger.json`)이 반복 간 발견 상태(Pass/open/recurred/accepted)를
  추적하고, 성공 선언 전 **최종 게이트** 리뷰어가 독립 확인하며, 잔여 Warning은 명시적
  처분(수용/이슈 발행/즉시 정리)을 받습니다. 끝난 런은 `.agent-review/runs/`에
  아카이브되어 다음 사이클과 대시보드가 읽습니다.
- **모델 라우팅은 사용자 소유**: repo당 한 번 `/init`을 실행해 루프 역할별
  모델(`developer` / `fixer` / `reviewer` / `gate`)을 직접 설정합니다
  (`.agent-review/config.json`). 루프는 설정을 그대로 따르며, 유일한 개입은
  리뷰어/게이트가 개발 모델보다 약하게 설정된 경우의 1회 경고입니다 — 루프는 심판의
  기준으로 수렴하므로 그 구성은 루프가 보장할 수 있는 상한을 낮춥니다. 통상적 선택:
  리뷰어·게이트에 최상위 모델, 개발·수정은 저렴한 티어.
- 구성 요소들은 모든 리뷰 리포트 끝의 기계가독 JSON 블록(`verdict`, `findings[]`)으로
  연동됩니다 — 이를 이용한 GitHub Actions 게이트·Stop 훅 레시피는
  [docs/ci.md](docs/ci.md) 참고.

`apply-review-findings` 스킬은 단독으로도 동작합니다: "리뷰 지적사항 반영해줘".

루프가 끝나면 번들된 `loop-dashboard` 스킬로 **한눈에 보는 대시보드**를 제안합니다 —
반복별 재시도 원인, Failed/Warning 추이 그래프, Pass로 해소된 항목, 목표 검증 결과.
자기완결 HTML(인라인 SVG 차트, CDN 의존 0)이라 플러그인과 함께 배포되고 오프라인에서도
동작합니다.

> 참고: 루프 호출 없이 모든 세션에 리뷰를 *강제*하려면 Claude Code
> [Stop 훅](https://docs.anthropic.com/en/docs/claude-code/hooks)을 본인 settings에
> 걸어 Failed 발견이 있으면 종료를 막게 하면 됩니다. 사용자별 하니스 설정이라 이
> 플러그인은 배포 대신 문서로 안내합니다.

## 구조

```
commands/
├── init.md                   # repo별 초기화: 역할→모델 설정, 원장 스캐폴딩
├── draft.md                  # draft-spec 전면 호출: 코드베이스+목표 분석 → 확정 명세
└── work.md                   # 목표 기반 develop→review→fix 루프 제어자
skills/
├── agent-work-review/
│   ├── SKILL.md              # 5-pass 리뷰 워크플로 본체 (+ 기계가독 결과 블록)
│   └── references/
│       ├── regression.md         # 소비자 추적, 직렬화 경계
│       ├── performance.md        # N+1, 무제한 읽기, sync-over-async
│       ├── cost.md               # 과금 모델 + Cosmos DB 딥다이브
│       ├── readability.md        # 에이전트 특유의 코드 냄새
│       ├── conventions.md        # repo 선례 발견·대조 방법
│       └── csharp-conventions.md # Microsoft C# 기본 컨벤션 (repo에 선례가 없을 때의 fallback)
├── draft-spec/
│   └── SKILL.md              # 없는 명세를 작성: 코드베이스 분석 → 목표 분석 → 확정 초안
├── apply-review-findings/
│   └── SKILL.md              # 리뷰 리포트의 Failed 발견 수정, 해소된 항목은 Pass로 보고
└── loop-dashboard/
    └── SKILL.md              # 루프 이력을 자기완결 HTML 대시보드로 렌더링
```

## 라이선스

MIT
