# HDTP 전환배치 최적화 제약 레퍼런스

## 개요

이 문서는 HDTP(전환배치) 최적화 시스템의 제약 전체 카탈로그이다.
어떤 LLM이든 이 문서를 컨텍스트로 제공받으면 CPLEX Infeasible 분석을 수행할 수 있다.

---

## 1. 시스템 개요

### 1.1 결정변수

- **형태**: `E{EMP_ID}.O{ORG_ID}` — 이진변수 (0 또는 1)
- **의미**: 직원 EMP_ID를 조직 ORG_ID에 배치하면 1, 아니면 0
- **생성 조건**: `AlgTotTO > StayEmpCnt`인 조직에만 변수 생성 (TO 여유가 있는 조직)

### 1.2 제약 분류 체계

| 분류 | CNST_GBN 값 | IsPenaltyCnst | 수학적 처리 | 위반 가능 여부 |
|------|-------------|---------------|-------------|---------------|
| **하드 제약** | `"제약"` | `false` | 등식/부등식 직접 추가 | **절대 불가** → Infeasible 원인 |
| **소프트 제약** | `"감점"` | `true` | 슬랙 변수 + 목적식 패널티 | 가능 (감점 부여) |

### 1.3 제약 등급 분류

| 등급 | 코드 범위 | 설명 | 사용자 변경 가능 |
|------|-----------|------|-----------------|
| 절대 제약 (CnstType=1) | TEAM001~TEAM010 | 시스템 기본 제약, 수정 불가 | 불가 |
| 필수 제약 (CnstType=2) | TEAM020~TEAM029 | 핵심 운영 제약 | 제한적 |
| 선택 제약 (CnstType=3) | TEAM030 이상 | 정책적 제약 | 가능 |

---

## 2. 최적화 파이프라인

```
1. MakeModel()              — 결정변수 생성 + TEAM001(TO) + TEAM002(필수이동) + TEAM003(1인1조직)
2. ApplyExcConstraint()     — 배타 제약 (징계 가해자/피해자 분리 등)
3. ApplyOrgConstraint()     — 조직 제약 (사업소 단위)
4. ApplyTeamConstraint()    — 팀 제약 (TEAM020~029, TEAM034, TEAM043~046)
5. ApplyPersonalConstraint()— 개인 제약 (TEAM030~042, TEAM047~048)
6. MakeObjective()          — 목적식 구성 (감점 최소화)
7. SolveWithOutCallback()   — CPLEX 최적화 수행
   ├─ 성공 → MakeResult()
   └─ 실패 → MakeConflictInfo() → IIS 분석
```

---

## 3. 제약 전체 카탈로그

### 3.1 절대 제약 (TEAM001~TEAM010)

| 코드 | 한글명 | Scope | 수학식 | 코드 위치 | Hard/Soft | 충돌 위험도 |
|------|--------|-------|--------|-----------|-----------|------------|
| **TEAM001** | TO 준수 | 조직(LVL5) | `Sum(배치변수) <= AlgTotTO - StayEmpCnt` | OptManager.cs:330-349 | 항상 Hard | **높음** — TEAM040과 충돌 빈발 |
| **TEAM002** | 필수이동 배치금지 | 개인 | `Sum(현부점 변수) = 0` | OptManager.cs:292-298 | 항상 Hard | 낮음 |
| **TEAM003** | 1인 1조직 배치 | 개인 | `Sum(전체변수) = 1` | OptManager.cs:323-325 | 항상 Hard | 낮음 |
| TEAM004~006 | (배타/가족관계 등) | 개인 | 배타 조건 | ApplyExcConstraint() | 항상 Hard | 낮음 |
| **TEAM007** | 직무 감점 매트릭스 | 개인 | 직무 전환 시 감점 | OptManager.cs:3210-3296 | 항상 Soft | 없음 |
| TEAM008~010 | (시스템 예약) | - | - | - | - | - |

### 3.2 필수 제약 — 팀 단위 (TEAM020~TEAM029)

| 코드 | 한글명 | Scope | 수학식 | 코드 위치 | Hard/Soft | 충돌 위험도 |
|------|--------|-------|--------|-----------|-----------|------------|
| **TEAM020** | 사업소 인원 상하한 | 사업소(LVL3) | `L <= Sum(배치변수) <= U` | OptManager.cs:3045-3098 | Hard / Soft 분기 | 중간 |
| **TEAM021** | 남성직원 1인 이상 | 팀/파트(LVL4/5) | `Sum(남성변수) >= 1` | OptManager.cs:1543-1641 | Hard / Soft 분기 | 낮음 |
| **TEAM022** | 팀내 전원이동 금지 | 팀(LVL4) | 2인 이상 팀에서 전원이동 방지 | OptManager.cs:1648-1708 | Hard / Soft 분기 | 낮음 |
| **TEAM023** | 동일팀→동일팀 이동불가 | 팀(LVL4) | 복수인원 동일팀→동일팀 불가 | OptManager.cs:1716-1781 | Hard / Soft 분기 | 낮음 |
| **TEAM024** | 고졸입사자 균등배분 | 팀(LVL4) | TO 기반 상한 제약 | OptManager.cs:1787-1853 | Hard / Soft 분기 | 중간 |
| **TEAM025** | 파트 전원이동 지양 | 파트(LVL5) | 전원이동 방지 | OptManager.cs:1863-1927 | 항상 Soft (PENALTY) | 없음 |
| **TEAM026** | 고년차직원 균등배분 | 팀(LVL4) | `Sum(고년차변수) <= limit` | OptManager.cs:1934-2008 | Hard / Soft 분기 | **높음** — TEAM040과 충돌 확인 (3차) |
| **TEAM027** | 직급연차 균등배분 | 팀(LVL4) | `L <= Sum <= U` | OptManager.cs:2466-2562 | Hard / Soft 분기 | 중간 |
| **TEAM028** | 선임 4년/5년 배치 | 파트(LVL5) | TO 2명 이상 시 연차 분배 | OptManager.cs:2571-2676 | Hard / Soft 분기 | 중간 |
| **TEAM029** | 고졸+고년차 동시배치 지양 | 파트(LVL5) | TO 2명일 때 동시배치 방지 | OptManager.cs:2790-2852 | 항상 Soft (PENALTY) | 없음 |

#### TEAM026 용량 산출 로직 (OptManager.cs:1961-1968)

```
TotTo >= 7 → limit = 4
TotTo >= 5 → limit = 2
TotTo >= 3 → limit = 1
TotTo < 3  → limit = 0 (배치 금지)
limit -= StayLongevity (잔류 고년차 차감)
```

### 3.3 선택 제약 — 개인 단위 (TEAM030~TEAM048)

| 코드 | 한글명 | Scope | 수학식 | 코드 위치 | Hard/Soft | 충돌 위험도 |
|------|--------|-------|--------|-----------|-----------|------------|
| **TEAM030** | 워킹맘 C지역 배치지양 | 개인 | `Sum(C지역변수) <= 0` | OptManager.cs:918-958 | Hard / Soft 분기 | **높음** — TEAM040과 충돌 확인 (1차) |
| **TEAM031** | 동일권역 이동지양 | 개인 | 동일 권역 배치 감점 | OptManager.cs:965-1005 | Hard / Soft 분기 | 낮음 |
| **TEAM032** | 직전근무지 지양 | 개인 | 직전 사업소 재배치 감점 | OptManager.cs:1011-1051 | Hard / Soft 분기 | 낮음 |
| **TEAM033** | 전환배치 18개월 미만 이동제한 | 개인 | 18개월 미만 이동 제한 | OptManager.cs:1058-1102 | Hard / Soft 분기 | 중간 |
| **TEAM034** | 성별 불균등 | 팀(LVL4) | 여담당 비율 60% 이상 시 감점 | OptManager.cs:2899-2970 | 항상 Soft (PENALTY) | 없음 |
| **TEAM035** | 24개월 이내 이동제한 | 개인 | 24개월 이내 이동 제한 | OptManager.cs:1108-1151 | Hard / Soft 분기 | 중간 |
| **TEAM036** | (사업소 단위 제약) | 사업소(LVL3) | - | OptManager.cs:3298-3351 | Hard / Soft 분기 | 낮음 |
| **TEAM037** | 직무이동 설정대상자만 변경 | 개인 | 미설정자 직무변경 금지 | OptManager.cs:1158-1202 | Hard / Soft 분기 | 중간 |
| **TEAM038** | 광역점 장기근무자 재배치 지양 | 개인 | C지역 장기근무→C/아울렛 지양 | OptManager.cs:1208-1248 | Hard / Soft 분기 | 낮음 |
| **TEAM039** | 신입 C지역 배치 금지 | 개인 | A/B지역 24개월 이하→C지역 금지 | OptManager.cs:1254-1294 | Hard / Soft 분기 | 중간 |
| **TEAM040** | 가능직무내 이동 | 개인 | `Sum(가능직무 조직변수) >= 1` | OptManager.cs:1301-1331 | **항상 Hard** (IsPenaltyCnst 분기 없음) | **매우 높음** — 모든 Infeasible의 수요 측 |
| **TEAM041** | 직무전환자 아울렛 지양 | 개인 | 아울렛 배치 감점 | OptManager.cs:1402-1453 | Hard / Soft 분기 | 낮음 |
| **TEAM042** | C지역→아울렛 재배치 지양 | 개인 | C지역 현근무→D지역 감점 | OptManager.cs:1460-1502 | Hard / Soft 분기 | 낮음 |
| **TEAM043** | 승진대상자 균등배치 | 팀(LVL4) | 팀단위 승진대상자 분배 | OptManager.cs:2073-2188 | Hard / Soft 분기 | 중간 |
| **TEAM044** | (TEAM043 연관) | 팀(LVL4) | 승진대상자 관련 | OptManager.cs:2268-2373 | Hard / Soft 분기 | 중간 |
| **TEAM045** | e-커머스 고년차 1명 이내 | 파트(LVL5) | `Sum(고년차변수) <= 1` | OptManager.cs:2016-2066 | Hard / Soft 분기 | 중간 |
| **TEAM046** | (연차 균등) | 파트(LVL5) | 연차 상하한 | OptManager.cs:2687-2781 | 항상 Soft (PENALTY) | 없음 |
| **TEAM047** | D지역 관련 | 개인 | D지역(아울렛) 배치 관련 | OptManager.cs:1508-1535 | Hard / Soft 분기 | 낮음 |
| **TEAM048** | 1순위/2순위 직무 보상 | 개인 | 직무 매칭 시 가점 | OptManager.cs:1337-1396 | 항상 Soft (보상) | 없음 |

---

## 4. TEAM040 — Infeasible의 핵심 수요 제약

### 왜 TEAM040이 항상 수요 측인가

- **항상 하드 제약**: `IsPenaltyCnst` 분기가 코드에 없음 → DB에서 "감점"으로 바꿔도 효과 없음
- **형태**: `Sum(가능직무 조직 변수) >= 1` → 최소 1개 조직에 반드시 배치
- **대상**: `PROP9`(가능직무)가 지정된 직원만
- **충돌 패턴**: 가능직무 조직이 다른 하드 제약에 의해 제한될 때 항상 Infeasible 발생

### 역사적 충돌 패턴

| 차수 | 충돌 상대 | 충돌 유형 | IIS 크기 | 부족분 |
|------|-----------|-----------|---------|--------|
| 1차 | TEAM030 (워킹맘 C지역 금지) | 개인 속성 충돌 | 2 | N/A |
| 2차 | TEAM001 (TO 상한) | 파트(LVL5) TO 부족 | 15 | 1슬롯 |
| 3차 | TEAM026 (고년차 균등배분) | 팀(LVL4) 용량 부족 | 21-24 | 1슬롯 |

---

## 5. DB 스키마 — MOVE_CASE_CNST_MASTER

| 컬럼 | 설명 | 용도 |
|------|------|------|
| FTR_MOVE_STD_ID | 전환배치 기준 ID | PK |
| CASE_ID | 케이스 ID | PK |
| CASE_DET_ID | 케이스 상세 ID | PK |
| REV_ID | 리비전 ID | PK |
| CNST_CD | 제약 코드 (TEAM001~048) | 제약 식별 |
| ORG_ID | 조직 ID | 조직별 제약 시 사용 |
| CNST_GBN | 제약 구분 ("제약" / "감점") | **하드/소프트 결정** |
| PENALTY_VAL | 감점 값 | 소프트 제약 시 목적식 패널티 |
| USE_YN | 사용 여부 (1/0) | 제약 활성화 |
| CNST_VAL | 제약 값 | 수치 파라미터 |
| VAL01~VAL04 | 추가 값 | 제약별 추가 파라미터 |
| TAG1 | 태그 (예: "여성,기혼") | 조건 필터 |

### IsPenaltyCnst 결정 로직

```csharp
// DataMOVE_CASE_CNST_MASTER_Ext.cs
public bool IsPenaltyCnst => CNST_GBN == "감점";
```

---

## 6. 관련 파일 경로

| 파일 | 경로 (trunk/src 기준) |
|------|----------------------|
| OptManager.cs | `Presentation/HDTP/HDTPManager/Models/OptManager.cs` |
| ConstraintModel.cs | `Presentation/HDTP/HDTPManager/Models/ConstraintModel.cs` |
| TransferPlanManager.cs | `Presentation/HDTP/HDTPManager/Models/TransferPlanManager.cs` |
| DataMOVE_CASE_CNST_MASTER_Ext.cs | `Infrastructure/InfrastructureHDTP/DataModels/HDTP/DataMOVE_CASE_CNST_MASTER_Ext.cs` |
| OrgModel.cs | `Presentation/HDTP/HDTPManager/Models/OrgModel.cs` |
| EmpModel.cs | `Presentation/HDTP/HDTPManager/Models/EmpModel.cs` |

---

## 7. 직원 분류 기준 (MakeEmpList 로직)

| 리스트 | 조건 | 코드 위치 |
|--------|------|-----------|
| TEAM020List | 전체 이동 대상자 | OptManager.cs:848 |
| TEAM021List | 남성 (`IsMale`) | OptManager.cs:849-850 |
| TEAM024List | 고졸입사 (`HightSchoolFinal`) | OptManager.cs:851-852 |
| TEAM026List | 고년차 (`PosLongevity`) | OptManager.cs:853-854 |
| TEAM027_L_List | 선임 4년 이하 (`ResearchEmpFourBelow`) | OptManager.cs:857-858 |
| TEAM027_U_List | 선임 5년 이상, 비고년차 | OptManager.cs:859-860 |
| TEAM029List | 고졸 또는 고년차 | OptManager.cs:855-856 |
| TEAM030List | 워킹맘 (`MarriedFemaleChildren`) | OptManager.cs:867-868 |
| TEAM031List | A/B/C/D 지역 근무 | OptManager.cs:869-870 |
| TEAM034List | 여성 (`IsFeMale`) | OptManager.cs:865-866 |
| TEAM037List | 직무변경 미설정 (`ChangeJobType2 == false`) | OptManager.cs:884-885 |
| TEAM038List | C지역 장기근무 (`C_AREA_WORK_MON >= 1`) | OptManager.cs:886-887 |
| TEAM039List | 24개월 이하 A/B 지역 | OptManager.cs:888-891 |
| TEAM040List | 가능직무 지정 (`PROP9 != null`) | OptManager.cs:892-895 |
| TEAM041List | A/B/C 지역 근무 | OptManager.cs:873-874 |
| TEAM042List | C지역 현근무 | OptManager.cs:875-876 |
| TEAM043_44List | 승진대상자 (`DegreeUpEmp == 1`) | OptManager.cs:901-903 |
| TEAM047List | D지역 근무 | OptManager.cs:871-872 |
| TEAM048List | PROP10/PROP11 지정 | OptManager.cs:896-899 |
