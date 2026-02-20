# Text2SQL HR 시스템

Local LLM 기반 Oracle SQL 자동 생성 시스템

한국어 자연어 질문을 Oracle SQL로 변환하고, HR 데이터베이스 조회 결과와 분석 보고서를 제공합니다.

## 주요 기능

- 자연어 → Oracle SQL 자동 변환 (LangChain + vLLM)
- 다중 LLM 모델 지원 (GPT-OSS 120B 메인, Qwen3-Coder 30B 테스트)
- 조회 결과 자연어 분석 보고서 자동 생성
- 모델 상태 실시간 헬스체크
- SQL 안전성 검증 (SELECT/WITH만 허용)
- Gradio 기반 웹 인터페이스

## 시스템 아키텍처

```
[사용자 브라우저] → [Gradio UI :7860] → [LangChain Pipeline]
                                              ↓            ↓
                                    [vLLM :8000/:8001]  [Oracle DB]
                                    [H100 GPU x5]       [HR 데이터]
```

## 기술 스택

| 구성요소 | 기술 |
|---------|------|
| LLM 서빙 | vLLM (H100 최적화) |
| 파이프라인 | LangChain + LangChain-OpenAI |
| 데이터베이스 | Oracle (oracledb Thin 모드) |
| 웹 UI | Gradio |
| 서버 | Rocky Linux 9.6, H100 NVL x5 |

## 빠른 시작

### 전체 구축 가이드
[docs/00-INDEX.md](docs/00-INDEX.md)에서 단계별 구축 가이드를 확인하세요.

### 문서 구조
| 문서 | 내용 |
|------|------|
| [00-INDEX](docs/00-INDEX.md) | 전체 문서 안내 (시작점) |
| [01-ARCHITECTURE](docs/01-ARCHITECTURE.md) | 시스템 아키텍처 이해 |
| [02-SERVER-SETUP](docs/02-SERVER-SETUP.md) | 서버 환경 확인 및 설정 |
| [03-PYTHON-ENV](docs/03-PYTHON-ENV.md) | Python 환경 구성 |
| [04-VLLM-DEPLOY](docs/04-VLLM-DEPLOY.md) | vLLM 모델 배포 |
| [05-ORACLE-DB](docs/05-ORACLE-DB.md) | Oracle DB 연결 |
| [06-APP-DEPLOY](docs/06-APP-DEPLOY.md) | 애플리케이션 배포 |
| [07-SERVICES](docs/07-SERVICES.md) | systemd 서비스 등록 |
| [08-TESTING](docs/08-TESTING.md) | 통합 테스트 |
| [09-OPERATIONS](docs/09-OPERATIONS.md) | 서버 운영 가이드 |
| [10-TROUBLESHOOTING](docs/10-TROUBLESHOOTING.md) | 문제 해결 |
| [11-MODEL-MANAGEMENT](docs/11-MODEL-MANAGEMENT.md) | 모델 관리 |
| [99-REFERENCE](docs/99-REFERENCE.md) | 참조 자료 |

## 프로젝트 구조

```
├── app/                    # 메인 애플리케이션
│   ├── app.py              # Gradio 웹 UI
│   ├── config.py           # 환경 설정 + MODEL_REGISTRY
│   ├── text2sql_pipeline.py # Text2SQL 핵심 파이프라인
│   ├── model_registry.py   # 모델 헬스체크
│   ├── db_setup.py         # Oracle DB 연결 테스트
│   └── .env.example        # 환경변수 템플릿
├── deploy/                 # 배포 자동화 스크립트
├── services/               # systemd 서비스 파일
├── docs/                   # 문서 시스템
├── CHANGELOG.md            # 변경 이력
└── OPERATIONS.md           # 서버 운영 가이드 (레거시)
```

## 환경 설정

```bash
# .env.example을 복사하여 .env 생성
cp app/.env.example app/.env

# 필수 환경변수 설정
ORACLE_PASSWORD=your_password
GRADIO_USER=admin
GRADIO_PASSWORD=your_password
```

## 라이선스

Private - Internal Use Only
