# CPLEX 생산계획 최적화 Infeasibility 분석 보고서

## 1. 개요

### 1.1 문제 현상
- 시스템: ALIS 마스터 플랜 (ScmMasterPlanManager)
- 조건: CASE_NO='KSHIFT', COMPANY_NO='1002', 조회기간 2025-06-01 ~ 2025-07-31
- 최적화 대상: 498건 ACT (83개 프로젝트, 8개 리소스)
- 오류: "해가 존재하지 않습니다. 제약위배사항을 확인하세요."

### 1.2 CPLEX 솔버 출력
```
Infeasibility row 'SCD000.P8202P1705.ACT014':  0  = 1.
Presolve time = 0.00 sec. (1.08 ticks)
Refine conflict on 1135 members...
→ 최종 11개 최소 충돌 집합 (Minimum Conflict Set)
```

### 1.3 분석 범위
- 소스 코드: OptManager.cs (CPLEX 모델 생성), ScmMasterPlanManager.xaml.cs (UI/실행), ScmCntrMasterPlanManager.cs (데이터 매니저)
- DB: STD_CALENDAR (캘린더), SCM_ACT_MASTER/DETAIL (작업 데이터), SCM_CASE_CNST_MASTER (제약 조건), SCM_RESOURCE_MASTER (리소스)
- LP 모델 파일 분석

---

## 2. CPLEX 최적화 모델 구조

### 2.1 결정 변수 (Decision Variables)
- 타입: 이진 정수 (0 또는 1)
- 형식: `{ACT_NO}.P{PROJECT_NO}.{ACT_NO}_{YYYYMMDD}`
- 의미: "해당 ACT가 해당 날짜에 완료되는가?" (1=예, 0=아니오)
- 생성 방식: PLN_FI(계획완료일)에서 역방향으로 durOffset(10)일 근무일분 생성
- 캘린더: STD_CALENDAR (MASTER) — AddCalDaysDt()로 근무일 계산

### 2.2 제약 조건 (21개 중 주요)

| 코드 | 이름 | 유형 | 수식 | 역할 |
|------|------|------|------|------|
| **SCD000** | 모든 ACT 일정생성 | 절대(Hard) | ∑(ACT의 날짜변수) = 1 | 모든 ACT에 정확히 1개의 완료일을 배정 |
| **SCD001** | 선착수 기간 제한 | 파라미터 | durOffset = 10 | 결정변수 생성 범위 (10근무일) |
| **SCD002** | 생산능력 준수 | 감점(Soft) | ∑(일별 물량) ≤ DAY_CAPA | 일일 생산능력 초과 시 패널티 |
| **SCD003** | 납기일 준수 | 절대 | EST_FI ≤ 납기일 | 납기 초과 불가 |
| **SCD004** | 휴일 근무 불가 | 절대 | 휴일에 일정 배정 불가 | 캘린더 기반 |
| **SCD005** | 선후행 역전 금지 | 절대 | 선행ACT 완료일 ≤ 후행ACT 시작일 | 작업 순서 보장 |

### 2.3 목적 함수
```
Minimize: ∑(패널티 변수 × 가중치)
```
SCD002의 용량 초과에 대한 감점(penalty=2)을 최소화

---

## 3. 오류 원인 분석

### 3.1 오류 메시지 해석

`Infeasibility row 'SCD000.P8202P1705.ACT014':  0  = 1`

| 구성요소 | 값 | 의미 |
|----------|----|----|
| SCD000 | 제약코드 | "모든 ACT 일정생성" 제약 |
| P8202P1705 | PROJECT_NO | 프로젝트 8202P1705 (철의장, 1658.37톤) |
| ACT014 | ACT_NO | 마킹팀(RES004) 작업 |
| 0 = 1 | 제약식 | 결정변수 합 = 0인데 1이어야 함 → 불가능 |

### 3.2 해당 ACT 상세 정보

| 항목 | 값 |
|------|-----|
| PROJECT_NO | 8202P1705 |
| ACT_NO | ACT014 |
| ACT_TYPE | B (마킹) |
| RESOURCE | RES004 (마킹팀) |
| PLN_ST / PLN_FI | 2025-07-11 / 2025-07-11 |
| EST_ST / EST_FI | 2025-06-30 / 2025-06-30 |
| STD_TRM | 1 (단일 근무일) |
| MUL_WGT | 1658.37 톤 |

프로젝트 8202P1705의 6개 ACT (ACT014~ACT019):
마킹(RES004) → 취부(RES005) → 용접(RES006) → 사상(RES003) → 도장(RES002) → 검사(RES007)

### 3.3 캘린더 검증 결과 (원인 제외)

| 항목 | 결과 |
|------|------|
| MASTER 캘린더 범위 | 2004-01-05 ~ 2032-12-31 (10,589일) |
| 2025년 6월 근무일 | 20일 |
| 2025년 7월 근무일 | 22일 |
| PLN_FI(07-11) 주변 10일 | 2025-06-27 ~ 07-11, 모두 근무일 포함 |
| 결론 | **캘린더 데이터는 정상** |

### 3.4 근본 원인: 다중 제약 조건 충돌

캘린더는 정상이므로, 결정변수는 정상적으로 생성되었으나 **다른 하드 제약 조건들의 조합**이 모든 후보 날짜를 배제:

```
ACT014의 후보 날짜: 2025-06-27 ~ 2025-07-11 (10개 근무일)
  ↓ SCD004 (휴일 불가): 토/일 제외 → 유효 날짜 감소
  ↓ SCD005 (선후행 역전 금지): 후행ACT(ACT015~019) 일정과 충돌
  ↓ SCD003 (납기일 준수): 납기일 이후 배정 불가
  ↓ SCD002 (용량 제약): 동일 날짜에 다른 프로젝트 ACT 물량 합산 → 초과
  ↓ 결과: 모든 날짜가 배제됨 → ∑(변수) = 0 → SCD000 위반
```

**Conflict Refinement 결과**: 1135개 제약 중 11개가 최소 충돌 집합
- 이 11개는 SCD000(일정생성) + SCD005(역전금지) 등의 조합으로 추정
- 특정 프로젝트 그룹에서 선후행 관계 + 좁은 일정 윈도우(10일)가 교착 상태 유발

### 3.5 핵심 원인 요약

| 원인 | 설명 | 영향도 |
|------|------|--------|
| **좁은 일정 윈도우** | durOffset=10일로 후보 날짜가 제한적 | 높음 |
| **선후행 관계 강제** | 6개 ACT의 순차 배정 필요 | 높음 |
| **대량 프로젝트 동시 배정** | 83개 프로젝트 × 6 ACT = 498건이 동일 리소스 경합 | 높음 |
| **일일 용량 제약** | RES004 DAY_CAPA=200, 프로젝트 당 ~1600톤 | 중간 |
| **코드 검증 부재** | 결정변수 0개 ACT에 대한 사전 감지 없음 | 중간 |

---

## 4. 해결 방안

### 4.1 Level 1: 즉시 조치 (데이터/파라미터 조정)

#### 방안 1-1: durOffset 확대 (SCD001 값 변경)
```sql
-- 현재: 10일 → 권장: 20~30일
UPDATE SCM_CASE_CNST_MASTER
SET CNST_VAL = 20
WHERE CASE_NO = 'KSHIFT' AND COMPANY_NO = '1002' AND CNST_CD = 'SCD001';
```
- 효과: 결정변수 후보 날짜가 10→20일로 확대, 제약 만족 가능성 증가
- 위험: 일정이 원래 계획에서 최대 20일까지 앞당겨질 수 있음
- 권장도: ★★★★★

#### 방안 1-2: LP 파일 분석으로 정확한 충돌 ACT 식별
```
LP 파일 위치: lp\plan_KSHIFT1002_{timestamp}.lp
분석 방법:
1. LP 파일에서 "SCD000" 제약 검색
2. 변수 계수가 0인 행(= 결정변수 없는 ACT) 식별
3. 해당 ACT의 데이터 확인 및 수정
```
- 권장도: ★★★★☆

#### 방안 1-3: 문제 프로젝트 일시 제외
```sql
-- 8202P1705 프로젝트의 MP_DT를 범위 밖으로 이동
-- (테스트 목적, 프로덕션에서는 비권장)
```
- 권장도: ★★☆☆☆ (임시 우회용)

### 4.2 Level 2: 코드 개선 (검증 강화)

#### 방안 2-1: 결정변수 사전 검증

파일: `OptManager.cs` — `InitOptVars()` 메서드 이후

```csharp
// 결정변수가 0개인 ACT 검출
List<string> zeroVarActs = new List<string>();
foreach (var optAct in planManager.OptActs)
{
    if (optAct.DecisionVars == null || optAct.DecisionVars.Count == 0)
    {
        zeroVarActs.Add($"P{optAct.dbAct.PROJECT_NO}.{optAct.dbAct.ACT_NO} " +
                        $"(PLN_FI={optAct.dbAct.DetailInfo.PLN_FI:yyyy-MM-dd})");
    }
}
if (zeroVarActs.Count > 0)
{
    throw new InvalidOperationException(
        $"결정변수 생성 실패 ACT {zeroVarActs.Count}건:\n" +
        string.Join("\n", zeroVarActs.Take(20)) +
        "\n\n원인: 캘린더 또는 durOffset 범위에 유효한 근무일이 없습니다.");
}
```

#### 방안 2-2: 모델 요약 로깅

파일: `ScmMasterPlanManager.xaml.cs` — `RunOptimization()` 메서드

```csharp
// MakeModel() 이후, Solve() 이전에 추가
string summary = PlanOptimizer.GetModelSummary();
// 출력: "모델 요약: ACT 498건, 결정변수 4,980개, 제약식 1,135개"
System.Diagnostics.Debug.WriteLine(summary);
```

#### 방안 2-3: MakeConflictInfo 사용자 친화적 메시지

파일: `OptManager.cs` — `MakeConflictInfo()` 메서드

현재: ConflictGridControl에 기술적 제약 코드만 표시
개선: 각 충돌 항목에 한국어 해설 + 해결 제안 추가

```csharp
// 충돌 항목별 진단 메시지 생성
if (cnstCd == "SCD000")
{
    conflict.Message = $"ACT {actNo}의 후보 날짜가 모두 다른 제약에 의해 배제됨";
    conflict.Suggestion = "SCD001(선착수기간) 값을 20 이상으로 확대하거나, " +
                          "선후행 관계/용량 제약을 검토하세요.";
}
else if (cnstCd == "SCD005" || cnstCd.StartsWith("SCD1"))
{
    conflict.Message = $"선행ACT {preActNo}와 후행ACT {aftActNo}의 일정이 역전됨";
    conflict.Suggestion = "해당 프로젝트의 PLN_ST/PLN_FI를 재조정하세요.";
}
```

#### 방안 2-4: 사전 진단 체크리스트 (ValidateBeforeOptimization)

파일: `ScmMasterPlanManager.xaml.cs` — `RunOptimizeILOG()` 메서드에 추가

```
체크 1: 캘린더 범위 ⊇ 전체 ACT PLN_FI 범위 (PASS)
체크 2: 모든 ACT PLN_FI ≠ NULL (PASS — 498건 모두 존재)
체크 3: durOffset 범위 내 근무일 ≥ STD_TRM (검증 필요)
체크 4: 선후행 관계 PLN_FI 순서 정합성 (검증 필요)
체크 5: 일별 리소스 물량 합 vs DAY_CAPA 비율 (검증 필요)
```

### 4.3 Level 3: 장기 개선 (사용자 경험)

#### 방안 3-1: 충돌 시각화 대시보드

기존 dp03(제약위배정보) 탭 상단에 요약 패널 추가:
- "11개 제약 위배: SCD000(일정생성) 3건, SCD005(역전금지) 8건"
- 심각도별 색상 코딩: 빨강(하드 위반) / 주황(소프트 위반)
- 간트 차트에 문제 ACT 빨간색 하이라이트

#### 방안 3-2: 자동 진단 시스템 (RunPreOptDiagnostics)

최적화 실행 전 자동 진단을 수행하여 사전에 문제를 감지:

```
┌──────────────────────────────────────────────────┐
│ 생산계획 최적화 사전 진단 결과                        │
│──────────────────────────────────────────────────│
│ ✅ 캘린더 범위: 정상 (2004~2032)                    │
│ ✅ PLN 일정: 498건 모두 설정됨                       │
│ ⚠️ 용량 초과 감지: RES004 7/7~7/11 (3,200/200톤)  │
│ ❌ 일정 윈도우 부족: P8202P1705.ACT014 (0일 여유)   │
│ ❌ 선후행 역전: P8202P1705 ACT014↔ACT015          │
│──────────────────────────────────────────────────│
│ 권장 조치:                                         │
│ 1. SCD001(선착수기간)을 10→20으로 확대             │
│ 2. P8202P1705의 PLN 일정 재조정                    │
│──────────────────────────────────────────────────│
│      [조치 후 재실행]  [무시하고 실행]  [취소]        │
└──────────────────────────────────────────────────┘
```

#### 방안 3-3: 제약 완화 옵션 UI

- "제약 완화" 버튼 추가 (리본 메뉴)
- 선택적 제약 해제 체크박스 (SCD000 → soft 변환 등)
- durOffset 슬라이더 (10~50일 범위 조절)
- 완화 후 재실행 기능

---

## 5. 사전 진단 SQL (운영용)

보고서에 아래 SQL을 첨부하여, 최적화 실행 전 문제를 사전에 발견할 수 있도록 합니다.

```sql
-- 진단 1: 결정변수 생성 가능 여부 (durOffset 범위 내 근무일 수)
-- (각 ACT의 PLN_FI 역방향 10근무일 범위 내 유효한 날짜가 있는지)
WITH act_dates AS (
    SELECT A.PROJECT_NO, A.ACT_NO, D.PLN_FI, D.RES_NO, D.MUL_WGT
    FROM SCM_ACT_MASTER A
    JOIN SCM_ACT_DETAIL D ON A.CASE_NO=D.CASE_NO AND A.COMPANY_NO=D.COMPANY_NO
         AND A.PROJECT_NO=D.PROJECT_NO AND A.ACT_NO=D.ACT_NO
    JOIN SCM_CONTRACT_MASTER B ON A.CASE_NO=B.CASE_NO AND A.COMPANY_NO=B.COMPANY_NO
         AND A.PROJECT_NO=B.PROJECT_NO
    WHERE A.CASE_NO = 'KSHIFT' AND A.COMPANY_NO = '1002'
    AND NVL(B.MP_DT, B.MP_INIT_DT) BETWEEN TO_DATE('2025-06-01','YYYY-MM-DD')
         AND TO_DATE('2025-07-31','YYYY-MM-DD')
    AND A.ACT_LEVEL = 2
)
SELECT ad.PROJECT_NO, ad.ACT_NO, ad.PLN_FI, ad.RES_NO, ad.MUL_WGT,
       (SELECT COUNT(*) FROM STD_CALENDAR c
        WHERE c.CAL_ID = 'MASTER'
        AND c.WRK_GBN = '1'
        AND TO_DATE(c.CAL_DAY,'YYYYMMDD') BETWEEN ad.PLN_FI - 14 AND ad.PLN_FI) AS avail_days
FROM act_dates ad
ORDER BY avail_days ASC, ad.PROJECT_NO, ad.ACT_NO;

-- 진단 2: 일별 리소스 물량 합산 (용량 초과 감지)
WITH act_dates AS (
    SELECT D.RES_NO, D.PLN_FI, SUM(D.MUL_WGT) AS total_wgt
    FROM SCM_ACT_DETAIL D
    JOIN SCM_ACT_MASTER A ON D.CASE_NO=A.CASE_NO AND D.COMPANY_NO=A.COMPANY_NO
         AND D.PROJECT_NO=A.PROJECT_NO AND D.ACT_NO=A.ACT_NO
    JOIN SCM_CONTRACT_MASTER B ON A.CASE_NO=B.CASE_NO AND A.COMPANY_NO=B.COMPANY_NO
         AND A.PROJECT_NO=B.PROJECT_NO
    WHERE A.CASE_NO = 'KSHIFT' AND A.COMPANY_NO = '1002'
    AND NVL(B.MP_DT, B.MP_INIT_DT) BETWEEN TO_DATE('2025-06-01','YYYY-MM-DD')
         AND TO_DATE('2025-07-31','YYYY-MM-DD')
    AND A.ACT_LEVEL = 2
    GROUP BY D.RES_NO, D.PLN_FI
)
SELECT ad.RES_NO, R.RESOURCE_NAME, ad.PLN_FI, ad.total_wgt, R.DAY_CAPA,
       ROUND(ad.total_wgt / NULLIF(R.DAY_CAPA, 0) * 100, 1) AS usage_pct
FROM act_dates ad
JOIN SCM_RESOURCE_MASTER R ON R.CASE_NO='KSHIFT' AND R.COMPANY_NO='1002' AND R.RESOURCE_NO=ad.RES_NO
WHERE ad.total_wgt > R.DAY_CAPA
ORDER BY usage_pct DESC;

-- 진단 3: 선후행 관계 역전 검출
SELECT R.PROJECT_NO, R.PRE_ACT_NO, R.AFT_ACT_NO,
       D1.PLN_FI AS pre_pln_fi, D2.PLN_ST AS aft_pln_st,
       CASE WHEN D1.PLN_FI > D2.PLN_ST THEN 'REVERSED' ELSE 'OK' END AS status
FROM SCM_ACT_RELATION R
JOIN SCM_ACT_DETAIL D1 ON R.CASE_NO=D1.CASE_NO AND R.COMPANY_NO=D1.COMPANY_NO
     AND R.PROJECT_NO=D1.PROJECT_NO AND R.PRE_ACT_NO=D1.ACT_NO
JOIN SCM_ACT_DETAIL D2 ON R.CASE_NO=D2.CASE_NO AND R.COMPANY_NO=D2.COMPANY_NO
     AND R.PROJECT_NO=D2.PROJECT_NO AND R.AFT_ACT_NO=D2.ACT_NO
WHERE R.CASE_NO = 'KSHIFT' AND R.COMPANY_NO = '1002'
AND D1.PLN_FI > D2.PLN_ST
ORDER BY R.PROJECT_NO;
```

---

## 6. 권장 조치 우선순위

| 순위 | 조치 | 예상 효과 | 소요 시간 | 위험도 |
|------|------|-----------|-----------|--------|
| 1 | SCD001 durOffset 10→20 확대 | 일정 윈도우 2배 확대, 해 발견 확률 대폭 증가 | 5분 (DB UPDATE) | 낮음 |
| 2 | LP 파일 분석으로 정확한 충돌 ACT 식별 | 11개 충돌 ACT 정확히 파악 | 1시간 | 없음 |
| 3 | 문제 프로젝트의 PLN 일정 재조정 | 선후행 역전 해소 | 30분 | 중간 |
| 4 | 사전 검증 코드 추가 (방안 2-1~2-4) | 향후 동일 문제 사전 방지 | 3~5일 | 낮음 |
| 5 | 자동 진단 시스템 구축 (방안 3-2) | 사용자가 직접 문제 파악 가능 | 10~15일 | 낮음 |

---

## 7. 향후 사용자 해결 방안 제시 방법

### 현재 문제점
- "해가 존재하지 않습니다"라는 메시지만 표시 → 사용자가 원인을 알 수 없음
- ConflictGridControl에 기술적 제약 코드(SCD000 등)만 표시 → 비전문가가 이해 불가

### 개선 방향

#### 단기 (1~2주)
1. **제약위배 메시지 한국어화**: "SCD000.P8202P1705.ACT014: 0=1" → "프로젝트 8202P1705의 마킹(ACT014) 작업에 배정 가능한 날짜가 없습니다"
2. **제약위배 요약**: "11건 위배 (일정생성 불가 3건, 선후행 역전 5건, 용량 초과 3건)"
3. **권장 조치 자동 생성**: 각 위배 항목에 "SCD001 값을 20으로 확대하세요" 등 구체적 조치 표시

#### 중기 (1~2달)
1. **사전 진단 다이얼로그**: 최적화 실행 전 5가지 체크 자동 수행, 문제 발견 시 경고
2. **제약 완화 UI**: 사용자가 특정 제약을 선택적으로 완화하고 재실행 가능
3. **What-If 분석**: durOffset 변경 시 영향 미리보기

#### 장기 (3~6달)
1. **지능형 제약 완화**: 충돌 시 자동으로 최소한의 제약을 완화하여 차선 해 제시
2. **대시보드**: 리소스별/기간별 부하 현황 + 제약 위배 히트맵
3. **학습 기반 추천**: 과거 해결 이력을 기반으로 유사 문제에 대한 조치 자동 추천

---

## 8. 결론

마스터 플랜 최적화의 Infeasibility는 **캘린더 문제가 아닌 다중 제약 조건 충돌**이 원인입니다. 498건 ACT가 8개 리소스를 놓고 경쟁하면서, 10일이라는 좁은 일정 윈도우(SCD001=10) 내에서 선후행 관계(SCD005)와 용량 제약(SCD002)을 동시에 만족하는 해가 존재하지 않습니다.

**즉시 조치**: SCD001(durOffset)을 10→20으로 확대하면 일정 윈도우가 2배로 넓어져 해를 찾을 가능성이 크게 증가합니다.

**근본 해결**: 최적화 실행 전 사전 진단 시스템을 도입하여, 문제가 될 수 있는 ACT와 제약 조건을 미리 식별하고 사용자에게 조치 방법을 안내하는 것이 필요합니다.

---

작성일: 2026-03-26
분석 도구: CPLEX Conflict Refinement, LP Model Analysis, Oracle DB Query
분석 대상: ALIS ScmMasterPlanManager (BlockFactoryManager)
