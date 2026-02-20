"""
모델 레지스트리 유틸리티
다중 vLLM 인스턴스의 상태 조회 및 Gradio UI 연동을 담당
"""
import logging
import urllib.request
import urllib.error

from config import MODEL_REGISTRY, DEFAULT_MODEL_KEY

logger = logging.getLogger(__name__)


def _check_health(base_url: str, timeout: float = 2.0) -> bool:
    """
    vLLM 인스턴스 헬스체크 (/v1/models 엔드포인트)

    Args:
        base_url: vLLM 서버 base URL (예: http://localhost:8000/v1)
        timeout: 요청 타임아웃 (초)

    Returns:
        True이면 서버가 정상 응답
    """
    url = base_url.rstrip("/") + "/models"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return True
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as e:
        logger.debug(f"헬스체크 실패 ({url}): {e}")
    return False


def get_available_models() -> list[dict]:
    """
    enabled=True인 모델 목록을 반환하고 각각의 헬스체크 결과를 포함

    Returns:
        [
            {
                "key": "gpt-oss-120b",
                "display_name": "GPT-OSS 120B (메인 추론 모델)",
                "base_url": "http://localhost:8000/v1",
                "model_name": "...",
                "gpu_info": "GPU 0-3 (TP4)",
                "description": "...",
                "healthy": True,
            },
            ...
        ]
    """
    results = []
    for key, cfg in MODEL_REGISTRY.items():
        if not cfg.get("enabled", False):
            continue
        healthy = _check_health(cfg["base_url"])
        results.append({
            "key": key,
            "display_name": cfg["display_name"],
            "base_url": cfg["base_url"],
            "model_name": cfg["model_name"],
            "gpu_info": cfg.get("gpu_info", ""),
            "description": cfg.get("description", ""),
            "healthy": healthy,
        })
    return results


def get_model_config(model_key: str) -> dict:
    """
    지정한 모델 키에 대응하는 base_url, model_name, max_tokens를 반환

    Args:
        model_key: MODEL_REGISTRY의 키 (예: "gpt-oss-120b")

    Returns:
        {"base_url": "...", "model_name": "...", "max_tokens": int}

    Raises:
        KeyError: 등록되지 않은 모델 키
    """
    if model_key not in MODEL_REGISTRY:
        raise KeyError(f"등록되지 않은 모델 키: {model_key}")
    cfg = MODEL_REGISTRY[model_key]
    return {
        "base_url": cfg["base_url"],
        "model_name": cfg["model_name"],
        "max_tokens": cfg.get("max_tokens", 4096),
    }


def get_display_choices() -> list[tuple[str, str]]:
    """
    Gradio Dropdown의 choices용 리스트 반환
    헬스체크를 수행하여 상태 표시를 포함

    Returns:
        [(label, key), ...] 형식
        예: [("GPT-OSS 120B (메인 추론 모델)", "gpt-oss-120b")]
    """
    models = get_available_models()
    choices = []
    for m in models:
        status_icon = "[정상]" if m["healthy"] else "[응답없음]"
        label = f"{status_icon} {m['display_name']}"
        choices.append((label, m["key"]))

    # enabled된 모델이 하나도 없으면 기본값이라도 표시
    if not choices:
        choices.append((f"[미등록] {DEFAULT_MODEL_KEY}", DEFAULT_MODEL_KEY))

    return choices
