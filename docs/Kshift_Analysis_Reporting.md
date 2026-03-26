---
layout: default
title: ILOG/CPLEX 비교 분석 리포팅
nav_order: 1
---

# ILOG/CPLEX 최적화 리포팅 기능 비교 분석 및 적용 방안 

> ALIS(조선소 생산관리) vs TPDemo(현대백화점 인사이동배치)

---

## 1. 개요

### 분석 배경

두 시스템 모두 **IBM ILOG/CPLEX** 최적화 엔진을 사용하여 자동 최적화를 수행하지만,
최적화 완료 후 **결과 리포팅 수준**에 큰 차이가 존재한다.

| 항목 | ALIS | TPDemo |
|------|------|--------|
| **도메인** | 조선소 블록 생산계획 최적화 | 백화점 인사 전환배치 최적화 |
| **최적화 대상** | ACT(작업) 일정 배정 | 직원 조직 배치 |
| **솔버** | CPLEX (ILP/MIP) | CPLEX (ILP/MIP) |
| **UI 프레임워크** | WPF + DevExpress | WPF + DevExpress |
| **버튼명** | `bOptimizeILOG` (생산계획 최적화) | `bOptimizeILOG` (자동배치) |

### 핵심 파일

| 프로젝트 | 파일 |
|----------|------|
| **ALIS** | `BlockFactoryManager/Views/ScmMasterPlanManager.xaml(.cs)` |
| **ALIS** | `BlockFactoryManager/Optimization/OptManager.cs` |
| **TPDemo** | `HDTPManager/Views/TPOptimization/MovePlanManager.xaml(.cs)` |
| **TPDemo** | `HDTPManager/Models/TransferPlanManager.cs` |

---

## 2. 최적화 실행 흐름 비교

### 공통 흐름 (동일)

```
사용자 클릭 → 확인 다이얼로그 → BackgroundWorker → CPLEX 모델 생성
→ 제약조건 적용 → 목적함수 설정 → LP파일 내보내기 → 솔버 실행
→ 성공: MakeResult() / 실패: MakeConflictInfo()
→ UI 스레드에서 결과 표시
```

### ALIS — 최적화 실행 (`RunOptimization`)

```csharp
// ScmMasterPlanManager.xaml.cs (line 1172)
private int RunOptimization()
{
    PlanOptimizer = new OptManager(dataManager, busyIndicator);
    PlanOptimizer.MakeModel();
    SetResCapacity();
    PlanOptimizer.ApplyConstraint(dataManager.ResActs);
    PlanOptimizer.MakeObjective();
    PlanOptimizer.ExportModel(modelFilename);  // LP 파일 내보내기

    if (PlanOptimizer.SolveWithOutCallback())
    {
        PlanOptimizer.MakeResult();
        MakeEstProdDays();  // EST_FI → EST_ST 역산
        return 1;           // 성공
    }
    else
    {
        PlanOptimizer.MakeConflictInfo();
        return -1;          // 실패
    }
}
```

### TPDemo — 최적화 실행 (`RunOptimization`)

```csharp
// TransferPlanManager.cs (line 3003)
public int RunOptimization()
{
    PlanOptimizer = new OptManager(this);
    CaclMustStayMoveEmp();
    UnAssingedItems.MakeAvailOrgInfo(OrgItems);

    PlanOptimizer.MakeModel();
    PlanOptimizer.ApplyPersonalConstraint();  // 개인 제약
    PlanOptimizer.ApplyTeamConstraint();      // 팀 제약
    PlanOptimizer.ApplyOrgConstraint();       // 조직 제약
    PlanOptimizer.ApplyExcConstraint();       // 배제 제약
    PlanOptimizer.MakeObjective();
    PlanOptimizer.ExportModel(modelFilename);

    if (PlanOptimizer.SolveWithOutCallback())
    {
        PlanOptimizer.MakeResult(UnAssingedItems);
        return 1;
    }
    else
    {
        PlanOptimizer.MakeConflictInfo(ConflictInfoType);
        return -1;
    }
}
```

> **실행 흐름은 거의 동일** — 차이는 제약조건 유형(생산 vs 인사)과 결과 후처리에서 발생

---

## 3. 결과 처리 비교 (핵심 차이점)

### ALIS — 현재 결과 처리 (단순)

```csharp
// ScmMasterPlanManager.xaml.cs (line 1583)
case WorkType.Optimization:
    if (result > 0)  // 성공
    {
        messageService.ShowMessage("최적 생산계획을 수립하였습니다.");
        ProjectPlanGridControl.ItemsSource = dataManager.Master;  // 그리드 바인딩
        PenaltyGridControl.ItemsSource = PlanOptimizer.penaltyItems;
        PlanOptimizer.ClearModel();
        ShowNextOptLoadChart();  // 부하 차트
    }
    else  // 실패
    {
        messageService.ShowWarning("해가 존재하지 않습니다. 제약위배사항을 확인하세요.");
        ConflictGridControl.ItemsSource = PlanOptimizer.conflictItems;
    }
```

### TPDemo — 결과 처리 (풍부한 리포팅)

```csharp
// MovePlanManager.xaml.cs (line 683)
case WorkType.Optimization:
    if (result > 0)  // 성공
    {
        messageService.ShowWarning("전환배치 최적화 수행완료.");

        // ★ 결과 데이터 변환 파이프라인
        MakeOptResult();                       // 미배치→배치 이동
        planManager.MakeBatchViewModel();      // 배치 결과 뷰모델 생성
        planManager.CalcCnstValue();           // 제약 값 재계산
        planManager.MakePersonalCnstInfo();    // 개인 제약 정보 생성

        // ★ 다중 그리드 바인딩
        OutboundGridControl.ItemsSource = planManager.BatchItems;   // Before
        InboundGridControl.ItemsSource = planManager.BatchItems;    // After
        PenaltyGridControl.ItemsSource = planManager.PenaltyItems;  // 패널티
    }
    else  // 실패
    {
        // ★ 위배 건수 포함 메시지
        messageService.ShowWarning($"해가 존재하지 않습니다. 제약위배 {conflictCount}건...");
        ConflictGridControl.ItemsSource = PlanOptimizer.conflictItems;

        // ★ 제약위배 요약 텍스트
        tbCnstSummary.Text = PlanOptimizer.conflictItems.GetConflictSummaryInfo();
    }
```

```csharp
// MakeOptResult 파이프라인 (line 786)
private void MakeOptResult()
{
    planManager.MakeOptResult();      // 배치 결과 생성
    planManager.MakePenaltyInfo();    // 런타임 패널티 집계
    planManager.MakePenltyInfoDB();   // DB 패널티 저장
}
```

---

## 4. 기능별 비교 분석표

| 기능 | ALIS (생산계획) | TPDemo (자동배치) | 격차 |
|------|:---:|:---:|:---:|
| **결과 메시지** | 단순 완료/실패 | 완료 + 위배 건수 | 부족 |
| **메인 결과 그리드** | 1개 (통합) | 2개 (Before/After) | **부족** |
| **패널티 그리드** | 런타임만 | 런타임 + DB 저장 | 부분 |
| **제약위배 그리드** | 그리드만 | 그리드 + 요약 텍스트 | **부족** |
| **결과 요약 대시보드** | — | GetConflictSummaryInfo() | **없음** |
| **다차원 피벗 분석** | 별도 뷰 (DB 기반) | 인라인 PivotGrid (인메모리) | **없음** |
| **결과 데이터 변환** | 직접 바인딩 | 파이프라인 (3단계) | **없음** |
| **그리드 간 네비게이션** | — | 클릭→필터/스크롤 | **없음** |
| **엑셀 내보내기** | 메인 그리드만 | 모든 그리드 개별 | 부족 |
| | | | |
| **부하 차트 (Before/After)** | chartLoadAnal1/2 | — | **ALIS 강점** |
| **간트 차트** | GanttActivityPanel | — | **ALIS 강점** |
| **3D/도면 뷰** | dp05/dp06 | — | **ALIS 강점** |

---

## 5. Gap 분석

### 핵심 Gap (즉시 개선 필요)

| # | Gap | 현재 상태 | 영향 |
|---|-----|-----------|------|
| 1 | **최적화 결과 요약 없음** | 단순 메시지만 표시 | 전체 결과 품질을 한눈에 파악 불가 |
| 2 | **Before/After 비교 없음** | PLN vs EST를 행별로 수동 비교 | 일정 변경 사항 파악에 시간 소요 |
| 3 | **제약위배 요약 없음** | 위배 건수/카테고리 집계 없음 | 문제 원인 파악이 어려움 |

### 중간 Gap (개선 권장)

| # | Gap | 현재 상태 | 영향 |
|---|-----|-----------|------|
| 4 | **인라인 피벗 분석 없음** | 별도 ScmPivotReportView 사용 | 최적화 결과의 다차원 분석 불편 |
| 5 | **그리드 간 네비게이션 없음** | 패널티/위배 → 메인 연동 없음 | 문제 ACT 추적에 수작업 필요 |

### 낮은 Gap

| # | Gap | 비고 |
|---|-----|------|
| 6 | 패널티 DB 저장 없음 | 실행 이력 비교 불가 |
| 7 | 개별 그리드 엑셀 내보내기 부족 | 메인 그리드만 지원 |

---

## 6. 적용 방안 (우선순위별)

### Priority 1: 최적화 결과 요약 패널

> 가장 빠르게 가치를 제공하는 개선

**구현 내용:**
- 최적화 성공 시: 총 패널티 점수, 리워드 점수, 일정 변경 ACT 수, 평균 이동일수
- 최적화 실패 시: 제약코드별 위배 건수 집계 (`GetConflictSummaryInfo()`)
- UI: 결과 탭 상단에 요약 TextBlock 추가

**참고 패턴 (TPDemo):**
```csharp
tbCnstSummary.Text = PlanOptimizer.conflictItems.GetConflictSummaryInfo();
// 출력 예: "TEAM020: 3건, TEAM040: 5건, LVL3: 2건 (총 10건)"
```

**수정 파일:**
- `OptManager.cs` — 요약 메서드 추가
- `ScmMasterPlanManager.xaml` — 요약 UI
- `ScmMasterPlanManager.xaml.cs` — 바인딩

---

### Priority 2: Before/After 일정변경 현황 그리드

> 생산 계획 담당자가 가장 필요로 하는 정보

**구현 내용:**
- 일정이 변경된 ACT만 필터하여 별도 그리드에 표시
- 변경 전(PLN_ST/FI) → 변경 후(EST_ST/FI) + 이동일수(Delta)
- 절대 Delta가 큰 순서로 정렬 (큰 변화 우선)

**데이터 예시:**

| PROJECT | ACT | RESOURCE | PLN_ST | PLN_FI | EST_ST | EST_FI | Delta(일) |
|---------|-----|----------|--------|--------|--------|--------|-----------|
| P001 | A003 | R01 | 03/01 | 03/15 | 03/20 | 04/03 | +19 |
| P002 | A001 | R02 | 03/10 | 03/25 | 03/05 | 03/20 | -5 |

**수정/생성 파일:**
- 새 모델: `OptScheduleChangeItem.cs`
- `ScmCntrMasterPlanManager.cs` — 변환 메서드
- `ScmMasterPlanManager.xaml(.cs)` — 새 탭 + 그리드

---

### Priority 3: 인라인 피벗 분석

> 다차원 교차 분석으로 최적화 결과의 깊은 인사이트 제공

**구현 내용:**
- 최적화 결과를 PivotGridControl로 즉시 분석
- 축 구성: 행(리소스, 계약구분) × 열(월) × 값(물량합, 공수합, ACT수)
- 더블클릭 드릴다운 (기존 ScmPivotReportView 패턴 재활용)

**참고 패턴 (TPDemo):**
```
행: 지역 → 사업부 → 팀 → 파트
열: 직종
값: 배치 인원수, 성별 분포, 근속연수
```

**ALIS 적용:**
```
행: 리소스 → 계약구분
열: 월 (EST_ST 기준)
값: MUL_WGT 합계, MHR_TOT 합계, ACT 건수
```

---

### Priority 4: 그리드 간 네비게이션 + 엑셀

**구현 내용:**
- 패널티/위배 그리드에서 항목 클릭 → 메인 그리드의 해당 ACT로 자동 스크롤
- 부하 차트에 해당 리소스 하이라이트
- 각 그리드에 개별 엑셀 내보내기 버튼

---

## 7. 재활용 가능한 기존 자산

| 자산 | 활용 방법 |
|------|-----------|
| `ScmPivotReportView.xaml` | PivotGrid + Chart XAML 패턴 복사 (SQL 로딩 제외) |
| `OptManager.cs` PenaltyModel | `GetSummaryInfo()` 메서드만 추가 |
| `OptManager.cs` ConflictModel | `GetConflictSummaryInfo()` 메서드만 추가 |
| 부하 차트 인프라 | Before/After 오버레이 차트로 확장 가능 |
| DockLayoutManager 패턴 | dp03~dp08과 동일 패턴으로 dp09/dp10 추가 |
| TPDemo `TotalRptModel.cs` | OptRptModel 설계 참고 (도메인 속성만 변경) |

---

## 8. 구현 로드맵

```
Priority 1 (1~2일)     Priority 2 (2~3일)     Priority 3 (3~4일)     Priority 4 (1~2일)
┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ 결과 요약     │───→│ 일정변경 현황     │───→│ 인라인 피벗 분석  │───→│ 네비게이션+엑셀  │
│ 패널         │    │ Before/After     │    │ PivotGrid+Chart  │    │ 그리드 간 연동   │
└──────────────┘    └──────────────────┘    └──────────────────┘    └─────────────────┘
  OptManager에        OptScheduleChange      OptRptModel 생성        CurrentItemChanged
  Summary 메서드       Item 모델 생성          PivotGrid XAML          이벤트 핸들러
  tbOptSummary UI     dp09 DocumentPanel     dp10 DocumentPanel      엑셀 버튼 추가
                      Delta 정렬              드릴다운 연동
```

**총 예상 기간: 7~11일**

---

## 9. 결론

| 관점 | 내용 |
|------|------|
| **TPDemo 참고 가치** | 결과 요약, Before/After, 피벗 분석, 그리드 네비게이션 패턴 |
| **ALIS 고유 강점** | 부하 차트, 간트 차트, 3D/도면 뷰 (유지 및 활용) |
| **핵심 개선** | "최적화 돌리고 끝"에서 → "결과를 분석하고 의사결정하는" 리포팅 체계로 전환 |
| **재활용율** | 기존 코드의 70% 이상 재활용 가능 (새 모델 2개 + 기존 확장) |
