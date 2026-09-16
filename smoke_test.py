"""One-command offline verification. Never calls OpenAI or uses the study database."""
import subprocess,sys
from pathlib import Path
if __name__=='__main__':
    raise SystemExit(subprocess.call([sys.executable,'-m','pytest','-q','tests'],cwd=Path(__file__).resolve().parent))
