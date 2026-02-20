#!/bin/bash
# =============================================================================
# Step 3: vLLM 설치 및 모델 서빙 설정
# =============================================================================
set -e

MINICONDA_DIR="/root/miniconda3"
ENV_NAME="text2sql"
ENV_BIN="$MINICONDA_DIR/envs/$ENV_NAME/bin"

echo "============================================"
echo " vLLM 설치"
echo "============================================"
echo ""

# conda 환경 활성화
export PATH="$MINICONDA_DIR/bin:$PATH"
source "$MINICONDA_DIR/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"

echo "[1] vLLM 설치..."
pip install vllm
echo ""

echo "[2] 설치 확인..."
python -c "import vllm; print(f'vLLM version: {vllm.__version__}')"
echo ""

echo "============================================"
echo " vLLM 설치 완료"
echo ""
echo " 모델 서빙 시작 (수동 테스트):"
echo ""
echo "  # 7B 모델로 빠른 테스트:"
echo "  python -m vllm.entrypoints.openai.api_server \\"
echo "      --model defog/sqlcoder-7b-2 \\"
echo "      --host 0.0.0.0 --port 8000"
echo ""
echo "  # 34B 모델 (프로덕션):"
echo "  python -m vllm.entrypoints.openai.api_server \\"
echo "      --model defog/sqlcoder-34b-alpha \\"
echo "      --tensor-parallel-size 2 \\"
echo "      --gpu-memory-utilization 0.90 \\"
echo "      --max-model-len 4096 \\"
echo "      --host 0.0.0.0 --port 8000"
echo "============================================"
