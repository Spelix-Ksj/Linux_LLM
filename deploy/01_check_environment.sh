#!/bin/bash
# =============================================================================
# Step 1-1: 서버 환경 확인 스크립트
# GPU, CUDA, 시스템 정보를 확인하고 출력
# =============================================================================
set -e

echo "============================================"
echo " H100 GPU 서버 환경 확인"
echo "============================================"
echo ""

# OS 정보
echo "[1] OS 정보"
cat /etc/os-release | head -4
echo ""

# CPU 정보
echo "[2] CPU 정보"
lscpu | grep -E "Model name|Socket|Core|Thread|CPU\(s\):" | head -5
echo ""

# 메모리 정보
echo "[3] 메모리 정보"
free -h
echo ""

# GPU 상태 확인
echo "[4] GPU 상태 (nvidia-smi)"
nvidia-smi
echo ""

# CUDA 버전 확인
echo "[5] CUDA 버전"
if command -v nvcc &> /dev/null; then
    nvcc --version
else
    echo "nvcc not found in PATH. Checking nvidia-smi for CUDA version..."
    nvidia-smi | grep "CUDA Version"
fi
echo ""

# GPU 토폴로지 (NVLink 연결 확인)
echo "[6] GPU 토폴로지 (NVLink)"
nvidia-smi topo -m
echo ""

# 디스크 공간 확인 (모델 다운로드를 위해 최소 100GB 필요)
echo "[7] 디스크 공간"
df -h / /root /tmp 2>/dev/null || df -h /
echo ""

echo "============================================"
echo " 환경 확인 완료"
echo "============================================"
