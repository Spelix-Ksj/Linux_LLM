# 05. Oracle DB 연결 설정

> **이 문서를 읽으면**: Text2SQL 시스템이 사용하는 Oracle 인사 DB에 접속하고, 대상 테이블 구조를 이해할 수 있습니다.
> **소요 시간**: 약 20분
> **선행 조건**: [04-LLM-SERVING.md](./04-VLLM-DEPLOY.md)
> **관련 스크립트**: deploy/05_oracle_db.sh

---

## 1. Oracle DB 접속 정보

Text2SQL 시스템은 본사(HQ) Oracle DB에 읽기 전용으로 접속합니다. 아래 표의 정보를 사용합니다.

| 항목 | 값 | 설명 |
|------|-----|------|
| **Host** | `HQ.SPELIX.CO.KR` | 본사 DB 서버 도메인 |
| **Port** | `7744` | Oracle 리스너 포트 (기본 1521이 아닌 커스텀 포트) |
| **SID** | `HISTPRD` | 인사(HIS) 운영(PRD) 데이터베이스 |
| **User** | `HRAI_CON` | HR AI 전용 읽기 계정 |
| **Password** | 환경변수로 관리 | `.env` 파일의 `ORACLE_PASSWORD`에 저장 |

> **왜 비밀번호를 환경변수로 관리합니까?**
> 코드에 비밀번호를 직접 쓰면 Git 저장소에 업로드될 위험이 있습니다.
> 환경변수(`.env` 파일)로 분리하면 코드와 비밀번호를 따로 관리할 수 있습니다.

---

## 2. Python 라이브러리 설치

Oracle DB에 접속하기 위해 Python 라이브러리 두 개를 설치합니다.

```bash
# text2sql 가상환경 활성화
conda activate text2sql

# 라이브러리 설치
pip install oracledb sqlalchemy
```

설치되는 라이브러리의 역할은 다음과 같습니다.

| 라이브러리 | 역할 |
|-----------|------|
| `oracledb` | Python에서 Oracle DB에 접속하는 드라이버입니다 |
| `sqlalchemy` | SQL을 Python 코드처럼 다룰 수 있게 해 주는 도구입니다 |

### oracledb Thin 모드란?

`oracledb` 라이브러리는 **Thin 모드**와 **Thick 모드** 두 가지가 있습니다.

| 모드 | Oracle Instant Client 설치 | 적용 방법 |
|------|---------------------------|----------|
| **Thin 모드** (기본값) | 불필요 | 별도 설정 없이 바로 사용 |
| Thick 모드 | 필요 | `oracledb.init_oracle_client()` 호출 필요 |

본 프로젝트는 **Thin 모드**를 사용합니다. Oracle Instant Client를 별도로 설치할 필요가 없으므로, 위의 `pip install` 명령만으로 설정이 완료됩니다.

> **Thin 모드가 무엇입니까?**
> 기존에는 Oracle DB에 접속하려면 Oracle사가 제공하는 별도 프로그램(Instant Client)을 설치해야 했습니다.
> Thin 모드는 이 과정 없이 순수 Python만으로 접속할 수 있는 방식입니다.
> 설치가 훨씬 간편합니다.

---

## 3. .env 파일 설정

`.env` 파일은 비밀번호, 인증 정보 등 민감한 설정값을 저장하는 파일입니다.

### 3.1 파일 위치

```
/root/text2sql/app/.env
```

### 3.2 .env 파일 생성

프로젝트에 `.env.example` 파일이 포함되어 있습니다. 이 파일을 복사하여 `.env` 파일을 만듭니다.

```bash
cd /root/text2sql/app

# .env.example을 복사하여 .env 생성
cp .env.example .env
```

> **`cp` 명령어란?**
> `cp`는 "copy"의 줄임말로, 파일을 복사하는 Linux 명령어입니다.
> `cp 원본파일 대상파일` 형식으로 사용합니다.

### 3.3 .env 파일 편집

```bash
# nano 편집기로 .env 파일 열기
nano .env
```

아래 세 개의 변수를 반드시 설정합니다.

```dotenv
# Oracle DB 비밀번호
ORACLE_PASSWORD=실제비밀번호입력

# Gradio 웹 UI 로그인 정보
GRADIO_USER=admin
GRADIO_PASSWORD=실제비밀번호입력
```

| 변수명 | 필수 여부 | 설명 |
|--------|----------|------|
| `ORACLE_PASSWORD` | 필수 | Oracle DB HRAI_CON 계정의 비밀번호 |
| `GRADIO_USER` | 필수 | 웹 UI 로그인 아이디 |
| `GRADIO_PASSWORD` | 필수 | 웹 UI 로그인 비밀번호 |

편집이 끝나면 `Ctrl + O` (저장) → `Enter` (확인) → `Ctrl + X` (종료)를 순서대로 누릅니다.

### 3.4 .env 파일 권한 설정

비밀번호가 담긴 파일이므로 소유자만 읽을 수 있도록 권한을 제한합니다.

```bash
chmod 600 .env
```

> **`chmod 600`이란?**
> 파일 권한을 "소유자만 읽기/쓰기 가능"으로 설정하는 명령어입니다.
> 다른 사용자가 이 파일을 열어 비밀번호를 볼 수 없습니다.

---

## 4. 네트워크 연결 확인

DB 서버에 접속하기 전에, 네트워크가 정상인지 먼저 확인합니다.

### 4.1 DNS 확인

도메인 이름이 IP 주소로 정상 변환되는지 확인합니다.

```bash
nslookup HQ.SPELIX.CO.KR
```

**정상 결과 예시:**

```
Server:    168.126.63.1
Address:   168.126.63.1#53

Name:      HQ.SPELIX.CO.KR
Address:   xxx.xxx.xxx.xxx     ← IP 주소가 출력되면 정상
```

**실패 시:**

```
** server can't find HQ.SPELIX.CO.KR: NXDOMAIN
```

이 경우 DNS 서버 설정을 확인합니다. `/etc/resolv.conf` 파일에 올바른 DNS 서버가 등록되어 있는지 점검합니다.

### 4.2 포트 연결 확인

DB 서버의 7744 포트에 접속할 수 있는지 확인합니다.

```bash
nc -zv HQ.SPELIX.CO.KR 7744
```

> **`nc` 명령어란?**
> `nc`(netcat)는 네트워크 연결을 테스트하는 도구입니다.
> `-z`는 데이터를 보내지 않고 연결만 확인하는 옵션이고,
> `-v`는 결과를 자세히 보여주는 옵션입니다.

**정상 결과:**

```
Connection to HQ.SPELIX.CO.KR 7744 port [tcp/*] succeeded!
```

**실패 시 확인 사항:**

| 증상 | 원인 | 해결 방법 |
|------|------|----------|
| `Connection timed out` | 방화벽 차단 | 네트워크 관리자에게 7744 포트 개방 요청 |
| `Connection refused` | DB 서비스 중지 | DB 관리자에게 리스너 상태 확인 요청 |
| `Name or service not known` | DNS 오류 | 4.1 DNS 확인부터 다시 수행 |

---

## 5. DB 연결 테스트

네트워크가 정상이면 Python 코드로 실제 DB 접속을 테스트합니다.

```bash
cd /root/text2sql/app && python db_setup.py
```

### 5.1 정상 실행 결과

```
============================================================
Oracle DB 연결 테스트
============================================================
연결 문자열: HRAI_CON@HQ.SPELIX.CO.KR:7744/HISTPRD
연결 성공

============================================================
테이블 스키마 조회
============================================================

[1/4] MOVE_ITEM_MASTER
  - EMP_NO        VARCHAR2(20)     직원번호
  - EMP_NM        VARCHAR2(100)    직원명
  - ORG_CD        VARCHAR2(20)     조직코드
  ...

[2/4] MOVE_ORG_MASTER
  ...

[3/4] MOVE_CASE_ITEM
  ...

[4/4] MOVE_CASE_CNST_MASTER
  ...

연결 성공 + 4개 테이블 스키마 출력 완료
```

### 5.2 오류 발생 시 대처

| 오류 메시지 | 원인 | 해결 방법 |
|------------|------|----------|
| `ORA-12541: TNS:no listener` | 리스너 미실행 | DB 관리자에게 리스너 시작 요청 |
| `ORA-01017: invalid username/password` | 비밀번호 오류 | `.env` 파일의 `ORACLE_PASSWORD` 확인 |
| `DPY-6005: cannot connect` | 네트워크 오류 | 4장의 네트워크 확인 절차 재수행 |
| `ModuleNotFoundError: oracledb` | 라이브러리 미설치 | `pip install oracledb` 재실행 |

---

## 6. 대상 테이블 스키마

Text2SQL 시스템이 질의하는 테이블은 총 **4개**입니다. 모두 인사 이동(Move) 관련 테이블입니다.

### 6.1 테이블 관계도 (ERD)

```
┌─────────────────────┐         ┌─────────────────────┐
│  move_item_master   │         │  move_org_master     │
│  (직원 정보)         │──org_cd──>│  (조직 정보)         │
│                     │         │                     │
│  emp_no (PK)        │         │  org_cd (PK)         │
│  emp_nm             │         │  org_nm              │
│  org_cd (FK)        │         │  parent_org_cd       │
└────────┬────────────┘         └─────────────────────┘
         │
         │ emp_no
         │
┌────────┴────────────┐         ┌─────────────────────┐
│  move_case_item     │         │move_case_cnst_master │
│  (배치안 상세)       │──case_id──>│  (제약조건)          │
│                     │         │                     │
│  case_id (FK)       │         │  case_id (PK)        │
│  emp_no (FK)        │         │  cnst_type           │
│  to_org_cd          │         │  cnst_value          │
└─────────────────────┘         └─────────────────────┘
```

**화살표 읽는 방법:**
- `──org_cd──>` : 왼쪽 테이블의 `org_cd` 컬럼이 오른쪽 테이블의 `org_cd`를 참조합니다.
- `──case_id──>` : 왼쪽 테이블의 `case_id` 컬럼이 오른쪽 테이블의 `case_id`를 참조합니다.

### 6.2 각 테이블 상세 설명

#### (1) move_item_master (직원 정보)

인사 이동 대상 **직원**의 기본 정보를 저장합니다.

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `emp_no` | VARCHAR2(20) | 직원번호 (기본키) |
| `emp_nm` | VARCHAR2(100) | 직원명 |
| `org_cd` | VARCHAR2(20) | 소속 조직코드 (외래키 → move_org_master) |
| `pos_nm` | VARCHAR2(50) | 직위명 (예: 과장, 부장) |
| `duty_nm` | VARCHAR2(50) | 직책명 (예: 팀장, 실장) |
| `join_dt` | DATE | 입사일 |

#### (2) move_org_master (조직 정보)

회사의 **조직**(부서) 구조를 저장합니다.

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `org_cd` | VARCHAR2(20) | 조직코드 (기본키) |
| `org_nm` | VARCHAR2(200) | 조직명 (예: 경영지원팀) |
| `parent_org_cd` | VARCHAR2(20) | 상위 조직코드 |
| `org_level` | NUMBER | 조직 단계 (1=본부, 2=실, 3=팀) |
| `use_yn` | CHAR(1) | 사용 여부 (Y/N) |

#### (3) move_case_item (배치안 상세)

인사 **배치안**(누가 어디로 이동하는지)의 개별 항목을 저장합니다.

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `case_id` | VARCHAR2(20) | 배치안 ID (외래키 → move_case_cnst_master) |
| `emp_no` | VARCHAR2(20) | 직원번호 (외래키 → move_item_master) |
| `from_org_cd` | VARCHAR2(20) | 이동 전 조직코드 |
| `to_org_cd` | VARCHAR2(20) | 이동 후 조직코드 |
| `move_dt` | DATE | 이동 예정일 |

#### (4) move_case_cnst_master (제약조건)

배치안에 적용된 **제약조건**(규칙)을 저장합니다.

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `case_id` | VARCHAR2(20) | 배치안 ID (기본키) |
| `cnst_type` | VARCHAR2(50) | 제약조건 유형 (예: 최소근무기간) |
| `cnst_value` | VARCHAR2(200) | 제약조건 값 (예: 24개월) |
| `case_nm` | VARCHAR2(200) | 배치안 명칭 |
| `create_dt` | DATE | 생성일 |

---

## 7. 확인 체크리스트

아래 항목을 모두 완료했는지 확인합니다. 체크가 안 되는 항목이 있으면 해당 절을 다시 읽어 주십시오.

```
[ ] oracledb, sqlalchemy 라이브러리 설치 완료
[ ] .env 파일 생성 및 ORACLE_PASSWORD 설정 완료
[ ] .env 파일 권한 600으로 설정 완료
[ ] nslookup 명령으로 DNS 확인 완료
[ ] nc 명령으로 7744 포트 연결 확인 완료
[ ] python db_setup.py 실행 → "연결 성공" + 4개 테이블 스키마 출력 확인
[ ] 4개 테이블의 역할과 관계 이해 완료
```

---
## 문서 탐색
| 이전 | 목차 | 다음 |
|------|------|------|
| [04-LLM-SERVING](./04-VLLM-DEPLOY.md) | [00-전체 안내](./00-INDEX.md) | [06-APP-DEPLOY](./06-APP-DEPLOY.md) |
