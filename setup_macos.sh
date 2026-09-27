#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "=============================================================="
echo " MediExplain+ Final — one-time macOS setup"
echo "=============================================================="

PY=""
if command -v python3.11 >/dev/null 2>&1; then
  PY=python3.11
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  echo "Python 3.11 is required. Install with: brew install python@3.11"
  exit 1
fi

command -v node >/dev/null 2>&1 || { echo "Node.js required: brew install node"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "npm is required."; exit 1; }
command -v ollama >/dev/null 2>&1 || { echo "Ollama required: brew install ollama"; exit 1; }

if ! command -v tesseract >/dev/null 2>&1; then
  echo "WARNING: Tesseract is not installed; prescription OCR will be unavailable."
  echo "Recommended: brew install tesseract tesseract-lang"
fi

echo
echo "[1/6] Backend environment"
cd backend
if [ ! -d .venv ]; then
  "$PY" -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m scripts.bootstrap_env

echo
echo "[2/6] Database migrations + demo accounts"
python - <<'PY'
from app.core.migrations import ensure_database
ensure_database()
print("Database is at the final migration.")
PY
python -m scripts.seed

echo
echo "[3/6] Real medication terminology (RxNorm)"
if python - <<'PY'
from app.services.medication_index import stats
raise SystemExit(0 if stats()["concepts"] > 100 else 1)
PY
then
  echo "Medication terminology already populated; preserving it."
else
  echo "Downloading/importing pinned RxNorm Current Prescribable Content..."
  python -m scripts.setup_medication_data || {
    echo "WARNING: RxNorm import failed (network unavailable?)."
    echo "Retry later: cd backend && source .venv/bin/activate && python -m scripts.setup_medication_data"
  }
fi

echo
echo "[4/6] Ollama model"
if ! ollama list 2>/dev/null | grep -q "llama3.1:8b"; then
  ollama pull llama3.1:8b
else
  echo "llama3.1:8b already installed."
fi
cd ..

echo
echo "[5/6] Frontend"
cd frontend
npm install
cd ..

echo
echo "[6/6] Optional extensions"
echo "Core system is installed."
echo "For diarisation + PaddleOCR research extensions:"
echo "  cd backend && source .venv/bin/activate"
echo "  pip install -r requirements-optional.txt"
echo "  # add HF_TOKEN=... to backend/.env after accepting pyannote model terms"
echo
echo "Optional pre-download of all Hugging Face weights:"
echo "  cd backend && source .venv/bin/activate && python -m scripts.preload_models"
echo
echo "Setup complete."
echo "Run: ./run_macos.sh"
