#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
cd ~/rex-ml
echo "### [1/3] rtx repo"
git -C rtx log --oneline -1
echo "### [2/3] uv env + torch"
rm -rf ~/rex-ml/.venv
uv venv --python 3.12 ~/rex-ml/.venv
VIRTUAL_ENV=~/rex-ml/.venv uv pip install torch numpy polars pyarrow tqdm
echo "### [3/3] verify"
~/rex-ml/.venv/bin/python -c "import torch;print('torch',torch.__version__,'cuda',torch.cuda.is_available(),torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO-GPU')"
cargo build --manifest-path ~/rex-ml/rtx/Cargo.toml 2>&1 | tail -3
df -h / | tail -1
echo "### STEP1-SETUP-DONE"
