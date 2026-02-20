#!/bin/bash
# =============================================================================
# 로컬 → 서버 파일 전송 스크립트
# Windows Git Bash 또는 WSL에서 실행
#
# 사용법:
#   bash upload_to_server.sh [사용자@서버IP]
#   bash upload_to_server.sh root@192.168.10.40
# =============================================================================

SERVER=${1:-"root@192.168.10.40"}
REMOTE_DIR="/root/text2sql"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================"
echo " 파일 업로드: $SERVER"
echo "============================================"
echo ""

# 서버에 디렉토리 생성
echo "[1] 원격 디렉토리 생성..."
ssh "$SERVER" "mkdir -p $REMOTE_DIR/{deploy,services}"

# 배포 스크립트 전송
echo "[2] 배포 스크립트 전송..."
scp "$SCRIPT_DIR/deploy/"*.sh "$SERVER:$REMOTE_DIR/deploy/"

# 서비스 파일 전송
echo "[3] 서비스 파일 전송..."
scp "$SCRIPT_DIR/services/"*.service "$SERVER:$REMOTE_DIR/services/"

# 앱 파일 전송
echo "[4] 애플리케이션 파일 전송..."
scp "$SCRIPT_DIR/app/"*.py "$SERVER:$REMOTE_DIR/"
scp "$SCRIPT_DIR/app/.env" "$SERVER:$REMOTE_DIR/"

# 실행 권한 부여
echo "[5] 실행 권한 설정..."
ssh "$SERVER" "chmod +x $REMOTE_DIR/deploy/*.sh"

echo ""
echo "============================================"
echo " 업로드 완료!"
echo ""
echo " 서버에 접속하여 배포를 시작하세요:"
echo "   ssh $SERVER"
echo "   cd $REMOTE_DIR"
echo "   bash deploy/deploy_all.sh"
echo "============================================"
