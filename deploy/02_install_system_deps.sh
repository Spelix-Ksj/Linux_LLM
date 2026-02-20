#!/bin/bash
# =============================================================================
# Step 1-2, 1-3: 시스템 패키지 설치 및 방화벽 설정
# =============================================================================
set -e

echo "============================================"
echo " 시스템 패키지 설치 및 방화벽 설정"
echo "============================================"
echo ""

# 개발 도구 및 라이브러리 설치
echo "[1] 개발 도구 설치..."
sudo dnf groupinstall -y "Development Tools"
sudo dnf install -y git wget curl bzip2 libffi-devel openssl-devel nc

echo ""
echo "[2] 방화벽 포트 개방..."

# 방화벽 활성화 여부 확인
if systemctl is-active --quiet firewalld; then
    # vLLM API 포트 (8000)
    sudo firewall-cmd --permanent --add-port=8000/tcp
    # Gradio 웹 UI 포트 (7860)
    sudo firewall-cmd --permanent --add-port=7860/tcp
    # 적용
    sudo firewall-cmd --reload
    echo "방화벽 포트 개방 완료 (8000, 7860)"
    sudo firewall-cmd --list-ports
else
    echo "firewalld가 비활성화 상태입니다. 방화벽 설정을 건너뜁니다."
fi

echo ""
echo "============================================"
echo " 시스템 설정 완료"
echo "============================================"
