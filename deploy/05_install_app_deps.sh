#!/bin/bash
# =============================================================================
# Step 4-6: 애플리케이션 Python 의존성 설치
# =============================================================================
set -e

MINICONDA_DIR="/root/miniconda3"
ENV_NAME="text2sql"
APP_DIR="/root/text2sql"

echo "============================================"
echo " 애플리케이션 의존성 설치"
echo "============================================"
echo ""

# conda 환경 활성화
export PATH="$MINICONDA_DIR/bin:$PATH"
source "$MINICONDA_DIR/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"

echo "[1] Oracle DB 드라이버 설치..."
pip install oracledb sqlalchemy
echo ""

echo "[2] LangChain 패키지 설치..."
pip install langchain langchain-openai langchain-community langchain-experimental
echo ""

echo "[3] 데이터 처리 패키지 설치..."
pip install pandas
echo ""

echo "[4] Gradio 웹 UI 설치..."
pip install gradio
echo ""

echo "[5] 애플리케이션 디렉토리 생성..."
mkdir -p "$APP_DIR"
echo "디렉토리 생성: $APP_DIR"
echo ""

echo "============================================"
echo " 의존성 설치 완료"
echo ""
echo " 다음 단계:"
echo "   1. app/ 폴더의 파일들을 $APP_DIR 로 복사"
echo "   2. .env 파일에서 DB 비밀번호 설정"
echo "   3. python db_setup.py 로 DB 연결 테스트"
echo "============================================"
