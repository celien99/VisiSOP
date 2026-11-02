# Install the CUDA torch build pinned in pyproject.toml and verify the GPU.
# Run this after cloning or after any `uv sync` that reinstalls the default
# CPU torch. The runtime/training process must be stopped first.

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    Write-Output "GPU:"
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader

    uv sync --extra train

    uv run python -c @"
import torch
print('torch', torch.__version__)
print('cuda_available', torch.cuda.is_available())
if torch.cuda.is_available():
    print('device', torch.cuda.get_device_name(0))
    torch.zeros(1, device='cuda')
    print('gpu_smoke_test', 'OK')
else:
    print('gpu_smoke_test', 'FAILED - install a CUDA-capable driver/torch build')
    raise SystemExit(1)
"@
} finally {
    Pop-Location
}
