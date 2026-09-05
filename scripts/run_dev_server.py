"""Dev-only launcher: loads .env (via python-dotenv) then starts uvicorn.
uvicorn itself does not auto-load .env files -- this script exists so
`python scripts/run_dev_server.py` behaves the same way whether run
from a shell that has .env sourced or not, and so a stale exported
DATABASE_URL never silently wins over .env (load_dotenv(override=True)
matches this repo's own documented pitfall: dotenv does NOT override
an already-exported env var by default, so `override=True` is required
here specifically because of that prior incident).
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv(override=True)

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import uvicorn

    port = int(os.environ.get("PORT", "8001"))
    uvicorn.run("app.api:app", host="127.0.0.1", port=port, reload=False)
