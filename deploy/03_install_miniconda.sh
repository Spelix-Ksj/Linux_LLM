#!/bin/bash
# =============================================================================
# Step 2: Miniconda 설치 및 Python 가상환경 구성
# =============================================================================
set -e

MINICONDA_DIR="/root/miniconda3"
ENV_NAME="text2sql"
PYTHON_VERSION="3.11"

echo "============================================"
echo " Miniconda 설치 및 가상환경 구성"
echo "============================================"
echo ""

# Miniconda 이미 설치되어 있는지 확인
if [ -d "$MINICONDA_DIR" ]; then
    echo "Miniconda가 이미 설치되어 있습니다: $MINICONDA_DIR"
else
    echo "[1] Miniconda 다운로드..."
    wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh

    echo "[2] Miniconda 설치..."
    bash /tmp/miniconda.sh -b -p "$MINICONDA_DIR"
    rm /tmp/miniconda.sh

    # 환경변수 설정
    echo "export PATH=\"$MINICONDA_DIR/bin:\$PATH\"" >> ~/.bashrc
    export PATH="$MINICONDA_DIR/bin:$PATH"

    # conda 초기화
    "$MINICONDA_DIR/bin/conda" init bash
    echo "Miniconda 설치 완료"
fi

# PATH 갱신
export PATH="$MINICONDA_DIR/bin:$PATH"

echo ""

# 가상환경 생성
if conda env list | grep -q "$ENV_NAME"; then
    echo "가상환경 '$ENV_NAME'이 이미 존재합니다."
else
    echo "[3] 가상환경 생성: $ENV_NAME (Python $PYTHON_VERSION)..."
    conda create -n "$ENV_NAME" python="$PYTHON_VERSION" -y
    echo "가상환경 생성 완료"
fi

echo ""
echo "============================================"
echo " Miniconda 및 가상환경 구성 완료"
echo ""
echo " 사용법:"
echo "   source ~/.bashrc"
echo "   conda activate $ENV_NAME"
echo "============================================"
