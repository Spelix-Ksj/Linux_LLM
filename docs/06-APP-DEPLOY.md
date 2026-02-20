# 06. Text2SQL 애플리케이션 배포

> **이 문서를 읽으면**: Text2SQL 애플리케이션의 전체 파일 구조를 이해하고, Windows에서 Linux로 파일을 전송하여 수동 실행까지 완료할 수 있습니다.
> **소요 시간**: 약 30분
> **선행 조건**: [05-ORACLE-DB.md](./05-ORACLE-DB.md)
> **관련 스크립트**: deploy/06_app_deploy.sh

---

## 1. 프로젝트 파일 구조

Text2SQL 애플리케이션은 `/root/text2sql/app/` 디렉토리에 위치합니다. 각 파일의 역할은 다음과 같습니다.

```
/root/text2sql/app/
│
├── .env                    # 환경변수 (비밀번호, 인증 정보)
├── .env.example            # .env 파일의 템플릿 (실제 비밀번호 없음)
│
├── config.py               # 설정 파일 + MODEL_REGISTRY (모델 목록)
├── db_setup.py             # Oracle DB 연결 테스트
├── model_registry.py       # vLLM 모델 헬스체크 (응답 가능 여부 확인)
│
├── text2sql_pipeline.py    # 핵심 파이프라인 (자연어 → SQL 변환)
├── app.py                  # Gradio 웹 UI (사용자 인터페이스)
│
└── test_e2e.py             # 통합 테스트 (전체 흐름 자동 검증)
```

### 1.1 파일 의존 관계 다이어그램

각 파일이 어떤 파일을 불러서(import) 사용하는지 보여줍니다. 화살표(`→`)는 "이 파일이 저 파일을 사용한다"는 뜻입니다.

```
                        .env
                         │
                         │ (환경변수 읽기)
                         ▼
                      config.py
                     ╱    │    ╲
                   ╱      │      ╲
                 ╱        │        ╲
               ▼          ▼          ▼
        db_setup.py  model_registry.py  text2sql_pipeline.py
                                              │
                                              │ (파이프라인 호출)
                                              ▼
                                           app.py
                                              │
                                              │ (테스트 대상)
                                              ▼
                                         test_e2e.py
```

**읽는 방법:**
- `.env` 파일에 저장된 환경변수를 `config.py`가 읽어옵니다.
- `config.py`의 설정값을 `db_setup.py`, `model_registry.py`, `text2sql_pipeline.py`가 각각 사용합니다.
- `app.py`는 `text2sql_pipeline.py`를 호출하여 웹 UI를 제공합니다.
- `test_e2e.py`는 `app.py`의 전체 흐름을 자동으로 테스트합니다.

---

## 2. 파일 전송 (Windows → Linux)

개발 PC(Windows)에서 작성한 파일을 Linux 서버로 전송합니다.

### 2.1 scp 명령으로 전송

Windows PowerShell 또는 터미널에서 아래 명령을 실행합니다.

```bash
scp -r "D:/Dev/Linux_LLM/app" root@192.168.10.40:/root/text2sql/app
```

| 부분 | 설명 |
|------|------|
| `scp` | Secure Copy의 줄임말입니다. SSH를 이용해 파일을 안전하게 전송합니다 |
| `-r` | 폴더 전체를 재귀적(recursive)으로 복사합니다 |
| `"D:/Dev/Linux_LLM/app"` | Windows에서 보낼 폴더 경로입니다 |
| `root@192.168.10.40` | Linux 서버 접속 정보 (사용자@IP주소)입니다 |
| `:/root/text2sql/app` | Linux에서 파일을 받을 경로입니다 |

> **비밀번호를 물어봅니까?**
> SSH 키를 설정하지 않았다면 `root` 사용자의 비밀번호를 입력해야 합니다.
> SSH 키 설정은 이전 문서를 참조합니다.

### 2.2 전송 확인

Linux 서버에 접속하여 파일이 제대로 전송되었는지 확인합니다.

```bash
ls -la /root/text2sql/app/
```

위에서 설명한 모든 파일이 목록에 나타나면 정상입니다.

---

## 3. Python 패키지 설치

Text2SQL 애플리케이션이 사용하는 Python 패키지를 설치합니다.

```bash
# text2sql 가상환경 활성화
conda activate text2sql

# 필요한 패키지 한 번에 설치
pip install langchain langchain-openai langchain-community oracledb sqlalchemy pandas gradio
```

각 패키지의 역할은 다음과 같습니다.

| 패키지명 | 역할 |
|----------|------|
| `langchain` | LLM(대규모 언어 모델)을 활용한 애플리케이션 개발 프레임워크입니다 |
| `langchain-openai` | LangChain에서 OpenAI 호환 API를 사용할 수 있게 합니다 (vLLM 포함) |
| `langchain-community` | LangChain 커뮤니티가 만든 추가 도구 모음입니다 |
| `oracledb` | Python에서 Oracle DB에 접속하는 드라이버입니다 |
| `sqlalchemy` | SQL을 Python 코드처럼 다룰 수 있게 해 주는 ORM 도구입니다 |
| `pandas` | 표 형태의 데이터를 처리하는 라이브러리입니다 (쿼리 결과 정리용) |
| `gradio` | 웹 UI를 간편하게 만들 수 있는 라이브러리입니다 |

> **패키지가 이미 설치되어 있으면 어떻게 됩니까?**
> `pip install`은 이미 설치된 패키지는 건너뛰므로, 중복 실행해도 문제가 없습니다.

---

## 4. .env 파일 설정

`.env` 파일 설정 방법은 이전 문서에 상세히 설명되어 있습니다.

**[05-ORACLE-DB.md의 3절 ".env 파일 설정"](./05-ORACLE-DB.md#3-env-파일-설정)** 을 참조합니다.

필수 환경변수를 다시 한번 정리합니다.

```dotenv
# Oracle DB 접속 비밀번호
ORACLE_PASSWORD=실제비밀번호

# Gradio 웹 UI 로그인 정보
GRADIO_USER=admin
GRADIO_PASSWORD=실제비밀번호
```

---

## 5. config.py 확인

`config.py`는 애플리케이션의 핵심 설정 파일입니다. 가장 중요한 부분은 **MODEL_REGISTRY**입니다.

### 5.1 MODEL_REGISTRY 구조

`MODEL_REGISTRY`는 사용 가능한 LLM 모델 목록을 딕셔너리(dictionary)로 관리합니다.

```python
MODEL_REGISTRY = {
    "gpt-oss-120b": {
        "base_url": "http://localhost:8000/v1",
        "model_name": "...",
        "description": "메인 Text2SQL 모델 (120B)"
    },
    "qwen3-coder": {
        "base_url": "http://localhost:8001/v1",
        "model_name": "...",
        "description": "보조 코딩 모델"
    },
    # ... 추가 모델 ...
}
```

| 키(key) | 설명 |
|---------|------|
| `base_url` | vLLM 서버의 API 주소입니다. 포트 번호로 서버를 구분합니다 |
| `model_name` | vLLM에 로드된 모델의 정확한 이름입니다 |
| `description` | 사람이 읽기 위한 모델 설명입니다 |

### 5.2 기본 모델 설정

```python
DEFAULT_MODEL_KEY = "gpt-oss-120b"
```

별도로 모델을 지정하지 않으면 `gpt-oss-120b` 모델이 사용됩니다. 이 모델은 포트 `8000`에서 동작하는 vLLM 메인 서비스에 연결됩니다.

> **모델을 변경하고 싶으면?**
> `config.py`에서 `DEFAULT_MODEL_KEY` 값을 `MODEL_REGISTRY`에 등록된 다른 키로 바꾸면 됩니다.
> 예를 들어, `"qwen3-coder"`로 변경하면 보조 모델이 기본으로 사용됩니다.

---

## 6. 수동 실행 테스트

서비스로 등록하기 전에, 수동으로 각 구성 요소가 정상 동작하는지 확인합니다.

### 6.1 파이프라인 단독 테스트

`text2sql_pipeline.py`는 자연어를 SQL로 변환하는 핵심 로직입니다. 단독으로 실행하여 테스트합니다.

```bash
cd /root/text2sql/app && python text2sql_pipeline.py
```

**정상 결과 예시:**

```
============================================================
Text2SQL 파이프라인 테스트
============================================================
입력: "경영지원팀 직원 목록을 보여주세요"
생성된 SQL:
  SELECT emp_no, emp_nm, pos_nm
  FROM move_item_master
  WHERE org_cd = (SELECT org_cd FROM move_org_master WHERE org_nm = '경영지원팀')

실행 결과: 15건 조회됨
============================================================
```

**오류 발생 시:**

| 오류 메시지 | 원인 | 해결 방법 |
|------------|------|----------|
| `ConnectionError: localhost:8000` | vLLM 서버 미실행 | vLLM 서비스를 먼저 시작합니다 |
| `ORA-xxxxx` | DB 연결 오류 | [05-ORACLE-DB.md](./05-ORACLE-DB.md) 5절 참조 |
| `ModuleNotFoundError` | 패키지 미설치 | 3절의 `pip install` 명령 재실행 |

### 6.2 Gradio 앱 수동 실행

웹 UI를 수동으로 실행하여 브라우저에서 접속할 수 있는지 확인합니다.

```bash
cd /root/text2sql/app && python app.py
```

**정상 결과 예시:**

```
Running on local URL:   http://0.0.0.0:7860
Running on public URL:  (비활성)

To create a public link, set `share=True` in `launch()`.
```

브라우저에서 `http://192.168.10.40:7860`에 접속합니다. `.env`에 설정한 `GRADIO_USER`와 `GRADIO_PASSWORD`로 로그인합니다.

> **수동 실행을 중지하려면?**
> 터미널에서 `Ctrl + C`를 누릅니다.

---

## 7. 보안 확인사항

Text2SQL 시스템은 DB에 직접 쿼리를 실행하므로 보안에 특히 주의해야 합니다.

### 7.1 SQL 안전성

| 항목 | 적용 여부 | 설명 |
|------|----------|------|
| SELECT만 허용 | 적용 | INSERT, UPDATE, DELETE, DROP 등 변경 쿼리를 차단합니다 |
| 읽기 전용 계정 | 적용 | `HRAI_CON` 계정은 DB에서 읽기 권한만 부여되어 있습니다 |
| SQL 검증 | 적용 | 생성된 SQL을 실행 전에 검증합니다 |

### 7.2 Gradio 인증

| 항목 | 적용 여부 | 설명 |
|------|----------|------|
| 로그인 필수 | 적용 | `.env`의 GRADIO_USER/PASSWORD로 인증합니다 |
| 인증 없이 접속 | 차단 | 로그인하지 않으면 어떤 기능도 사용할 수 없습니다 |

### 7.3 결과 행 제한

| 항목 | 적용 여부 | 설명 |
|------|----------|------|
| 최대 1,000행 제한 | 적용 | 쿼리 결과가 1,000행을 초과하면 잘라서 보여줍니다 |
| 의도 | - | 대량 데이터 유출을 방지하고 서버 부하를 줄입니다 |

---

## 8. 확인 체크리스트

아래 항목을 모두 완료했는지 확인합니다.

```
[ ] scp로 Windows → Linux 파일 전송 완료
[ ] ls -la로 /root/text2sql/app/ 파일 목록 확인 완료
[ ] pip install로 7개 패키지 설치 완료
[ ] .env 파일 설정 완료 (05-ORACLE-DB.md 참조)
[ ] config.py의 MODEL_REGISTRY 내용 확인 완료
[ ] python text2sql_pipeline.py 수동 테스트 성공
[ ] python app.py 수동 실행 → 브라우저에서 웹 UI 접속 확인
[ ] 보안 항목 3가지 (SQL 안전성, Gradio 인증, 1000행 제한) 이해 완료
```

---
## 문서 탐색
| 이전 | 목차 | 다음 |
|------|------|------|
| [05-ORACLE-DB](./05-ORACLE-DB.md) | [00-전체 안내](./00-INDEX.md) | [07-SERVICES](./07-SERVICES.md) |
