#!/bin/bash
# =============================================================================
# 마스터 배포 스크립트
# 전체 Text2SQL 시스템을 단계별로 설치
#
# 사용법:
#   # 전체 설치 (서버에서 실행):
#   bash deploy_all.sh
#
#   # 특정 단계부터 실행:
#   bash deploy_all.sh --from 3
#
#   # 특정 단계만 실행:
#   bash deploy_all.sh --step 4
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="/root/text2sql"
FROM_STEP=${FROM_STEP:-1}
ONLY_STEP=""

# 인자 파싱
while [[ $# -gt 0 ]]; do
    case $1 in
        --from)
            FROM_STEP="$2"
            shift 2
            ;;
        --step)
            ONLY_STEP="$2"
            shift 2
            ;;
        *)
            echo "사용법: $0 [--from N] [--step N]"
            exit 1
            ;;
    esac
done

should_run() {
    local step=$1
    if [ -n "$ONLY_STEP" ]; then
        [ "$step" -eq "$ONLY_STEP" ]
    else
        [ "$step" -ge "$FROM_STEP" ]
    fi
}

echo ""
echo "########################################################"
echo "#  H100 Text2SQL 시스템 배포 스크립트"
echo "########################################################"
echo ""

# --- Step 1: 환경 확인 ---
if should_run 1; then
    echo ""
    echo ">>> Step 1: 서버 환경 확인"
    echo "---"
    bash "$SCRIPT_DIR/01_check_environment.sh"
    echo ""
    read -p "환경이 정상적으로 보이나요? 계속하려면 Enter... (Ctrl+C로 중단)"
fi

# --- Step 2: 시스템 패키지 ---
if should_run 2; then
    echo ""
    echo ">>> Step 2: 시스템 패키지 설치 및 방화벽 설정"
    echo "---"
    bash "$SCRIPT_DIR/02_install_system_deps.sh"
fi

# --- Step 3: Miniconda ---
if should_run 3; then
    echo ""
    echo ">>> Step 3: Miniconda 설치 및 가상환경 구성"
    echo "---"
    bash "$SCRIPT_DIR/03_install_miniconda.sh"
    export PATH="/opt/miniconda3/bin:$PATH"
fi

# --- Step 4: vLLM ---
if should_run 4; then
    echo ""
    echo ">>> Step 4: vLLM 설치"
    echo "---"
    bash "$SCRIPT_DIR/04_install_vllm.sh"
fi

# --- Step 5: 앱 의존성 ---
if should_run 5; then
    echo ""
    echo ">>> Step 5: 애플리케이션 의존성 설치"
    echo "---"
    bash "$SCRIPT_DIR/05_install_app_deps.sh"
fi

# --- Step 6: 앱 파일 배포 ---
if should_run 6; then
    echo ""
    echo ">>> Step 6: 애플리케이션 파일 배포"
    echo "---"
    mkdir -p "$APP_DIR"
    mkdir -p "$APP_DIR/services"

    # 앱 파일 복사 (deploy 스크립트가 있는 위치의 상위 디렉토리에서)
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
    cp "$PROJECT_ROOT/app/"*.py "$APP_DIR/"
    cp "$PROJECT_ROOT/app/.env" "$APP_DIR/"
    cp "$PROJECT_ROOT/services/"*.service "$APP_DIR/services/"

    echo "  앱 파일 배포 완료: $APP_DIR"
    ls -la "$APP_DIR/"
fi

# --- Step 7: 서비스 등록 ---
if should_run 7; then
    echo ""
    echo ">>> Step 7: systemd 서비스 등록"
    echo "---"
    bash "$SCRIPT_DIR/06_setup_services.sh"
fi

echo ""
echo "########################################################"
echo "#  배포 완료!"
echo "#"
echo "#  다음 단계:"
echo "#  1. vLLM 서버 시작: sudo systemctl start vllm"
echo "#     (모델 다운로드 + 로딩에 시간이 걸립니다)"
echo "#  2. vLLM 상태 확인: journalctl -u vllm -f"
echo "#  3. vLLM 준비 확인: curl http://localhost:8000/v1/models"
echo "#  4. DB 연결 테스트: cd $APP_DIR && python db_setup.py"
echo "#  5. 웹 UI 시작: sudo systemctl start text2sql-ui"
echo "#  6. 브라우저 접속: http://<서버IP>:7860"
echo "#"
echo "#  먼저 7B 모델로 테스트하려면:"
echo "#    sudo systemctl start vllm-7b  (vllm 대신)"
echo "#    .env 파일에서 VLLM_MODEL=defog/sqlcoder-7b-2 로 변경"
echo "########################################################"
