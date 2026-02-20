#!/bin/bash
# =============================================================================
# Step 7: systemd 서비스 등록
# 서비스 파일 복사 및 활성화
# =============================================================================
set -e

APP_DIR="/root/text2sql"
SERVICES_SRC="$APP_DIR/services"

echo "============================================"
echo " systemd 서비스 등록"
echo "============================================"
echo ""

# 서비스 파일 복사
echo "[1] 서비스 파일 복사..."
sudo cp "$SERVICES_SRC/vllm.service" /etc/systemd/system/
sudo cp "$SERVICES_SRC/vllm-7b.service" /etc/systemd/system/
sudo cp "$SERVICES_SRC/text2sql-ui.service" /etc/systemd/system/
echo "  완료"
echo ""

# systemd 리로드
echo "[2] systemd 리로드..."
sudo systemctl daemon-reload
echo "  완료"
echo ""

# 서비스 활성화 (부팅 시 자동 시작)
echo "[3] 서비스 활성화..."
sudo systemctl enable vllm
sudo systemctl enable text2sql-ui
echo "  완료"
echo ""

echo "============================================"
echo " 서비스 등록 완료"
echo ""
echo " 사용법:"
echo "   # 7B 모델로 테스트 시작:"
echo "   sudo systemctl start vllm-7b"
echo ""
echo "   # 34B 모델 프로덕션 시작:"
echo "   sudo systemctl start vllm"
echo ""
echo "   # 웹 UI 시작:"
echo "   sudo systemctl start text2sql-ui"
echo ""
echo "   # 상태 확인:"
echo "   sudo systemctl status vllm"
echo "   sudo systemctl status text2sql-ui"
echo ""
echo "   # 로그 확인:"
echo "   journalctl -u vllm -f"
echo "   journalctl -u text2sql-ui -f"
echo "============================================"
