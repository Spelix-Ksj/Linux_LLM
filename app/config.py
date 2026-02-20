"""
환경 설정 로더
.env 파일에서 설정을 읽어 애플리케이션에 제공
"""
import os
from pathlib import Path

# .env 파일 로드 (python-dotenv 없이 직접 파싱)
def _load_env():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    # 이미 환경변수에 설정된 값이 있으면 그것을 우선
                    if key not in os.environ:
                        os.environ[key] = value

_load_env()


# Oracle DB 설정
DB_CONFIG = {
    "user": os.environ.get("ORACLE_USER", "HRAI_CON"),
    "password": os.environ.get("ORACLE_PASSWORD", ""),
    "host": os.environ.get("ORACLE_HOST", "HQ.SPELIX.CO.KR"),
    "port": int(os.environ.get("ORACLE_PORT", "7744")),
    "sid": os.environ.get("ORACLE_SID", "HISTPRD"),
}

# 대상 테이블 목록
TARGET_TABLES = [
    "move_item_master",
    "move_case_item",
    "move_case_cnst_master",
    "move_org_master",
]

# vLLM 설정 (하위 호환용 — 기존 코드에서 직접 참조하는 경우를 위해 유지)
VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
VLLM_MODEL = os.environ.get("VLLM_MODEL", "defog/sqlcoder-34b-alpha")

# ===== 모델 레지스트리 (다중 vLLM 인스턴스 지원) =====
MODEL_REGISTRY = {
    "qwen3-coder-30b": {
        "display_name": "Qwen3-Coder 30B (테스트)",
        "base_url": os.environ.get("VLLM_BASE_URL_1", "http://localhost:8001/v1"),
        "model_name": "Qwen3-Coder-30B-A3B-Instruct",
        "gpu_info": "GPU 4",
        "description": "테스트/비교용 모델 — Qwen3 코딩 MoE (30B, 활성 3B)",
        "max_tokens": 4096,
        "enabled": True,
    },
    # Arctic-Text2SQL-R1-7B (사용 중지 — SQLite 전용, Oracle 비호환)
    # "arctic-text2sql-7b": {
    #     "display_name": "Arctic-Text2SQL-R1-7B (SQLite 전문)",
    #     "base_url": os.environ.get("VLLM_BASE_URL_1", "http://localhost:8001/v1"),
    #     "model_name": "Arctic-Text2SQL-R1-7B",
    #     "gpu_info": "GPU 4",
    #     "description": "Snowflake Text2SQL 모델 (BIRD 68.9%, SQLite 전용)",
    #     "max_tokens": 4096,
    #     "enabled": True,
    # },
    "gpt-oss-120b": {
        "display_name": "GPT-OSS 120B (메인 추론 모델)",
        "base_url": os.environ.get("VLLM_BASE_URL_0", "http://localhost:8000/v1"),
        "model_name": os.environ.get("VLLM_MODEL_0", "/install_file_backup/tessinu/gpt-oss-120b"),
        "gpu_info": "GPU 0-3 (TP4)",
        "description": "OpenAI 범용 추론 모델 (MoE 117B)",
        "max_tokens": 4096,
        "enabled": True,
    },
    # EXAONE Deep 32B (사용 중지 — 필요 시 재활성화)
    # "exaone-deep-32b": {
    #     "display_name": "EXAONE Deep 32B (한국어 특화)",
    #     "base_url": os.environ.get("VLLM_BASE_URL_1", "http://localhost:8001/v1"),
    #     "model_name": "EXAONE-Deep-32B",
    #     "gpu_info": "GPU 4",
    #     "description": "LG AI Research 한국어 추론 모델 (32B)",
    #     "max_tokens": 1024,
    #     "enabled": True,
    # },
    # Qwen3-30B-A3B (GPU 4 교체용 — EXAONE 중지 후 사용)
    # "qwen3-30b": {
    #     "display_name": "Qwen3 30B A3B Thinking (보조 모델)",
    #     "base_url": os.environ.get("VLLM_BASE_URL_1", "http://localhost:8001/v1"),
    #     "model_name": "Qwen3-30B-A3B-Thinking",
    #     "gpu_info": "GPU 4",
    #     "description": "Qwen3 MoE 추론 모델 (30B, FP8)",
    #     "max_tokens": 4096,
    #     "enabled": True,
    # },
}

# 기본 모델 키 (UI 초기값 및 model_key=None일 때 사용)
DEFAULT_MODEL_KEY = "gpt-oss-120b"

# Gradio 설정
GRADIO_HOST = os.environ.get("GRADIO_HOST", "0.0.0.0")
GRADIO_PORT = int(os.environ.get("GRADIO_PORT", "7860"))
