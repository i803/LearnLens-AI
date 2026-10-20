from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Load a repository-local .env explicitly so that the presence of a real
# configuration file is distinguishable from a clean judge checkout. A local
# checkout with no .env gets the offline walkthrough; configured or hosted
# deployments must never expose the synthetic teacher classroom.
BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
_ENV_CANDIDATES = (Path.cwd() / ".env", BACKEND_DIR / ".env", PROJECT_DIR / ".env")
ENV_FILE_PATH = next((candidate.resolve() for candidate in _ENV_CANDIDATES if candidate.is_file()), None)
# Treat .env variants in any app directory as an intentional real-data setup,
# including web/.env.local used by the Next.js proxy. .env.example is safe to commit
# and must not disable the clean-checkout judge demo by itself.
_ENV_DIRS = (PROJECT_DIR, BACKEND_DIR, PROJECT_DIR / "web")
ENV_FILE_PRESENT = any(
    candidate.is_file() and candidate.name.startswith(".env") and candidate.name != ".env.example"
    for directory in _ENV_DIRS
    for candidate in directory.glob(".env*")
)
if ENV_FILE_PATH:
    load_dotenv(dotenv_path=ENV_FILE_PATH, override=False)
else:
    load_dotenv()


def is_hosted_environment() -> bool:
    """Return True for Vercel and common managed/production environments."""
    if any(os.getenv(name, "").strip() for name in ("VERCEL", "VERCEL_ENV", "RENDER", "RAILWAY_ENVIRONMENT", "DYNO")):
        return True
    return any(
        os.getenv(name, "").strip().lower() in {"production", "staging"}
        for name in ("APP_ENV", "ENVIRONMENT", "DEPLOYMENT_ENV", "NODE_ENV")
    )


OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip()
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip().rstrip("/")
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "http://localhost:3000").strip()
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "LearnLens AI").strip()
OPENROUTER_TIMEOUT_SECONDS = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "25"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").strip().rstrip("/")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "").strip()
AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() == "true"

# If DEMO_MODE is omitted, a clean local checkout defaults to the offline
# judge walkthrough. The existence of .env or real service credentials opts
# the backend into real-data mode. Hosting is checked separately below, so a
# mistakenly set DEMO_MODE=true on Vercel cannot expose sample students.
_EXPLICIT_DEMO_MODE = os.getenv("DEMO_MODE")
_HAS_REAL_SERVICE_CONFIG = bool(SUPABASE_URL or SUPABASE_SECRET_KEY or OPENROUTER_API_KEY or GEMINI_API_KEY)
if _EXPLICIT_DEMO_MODE is not None:
    DEMO_MODE = _EXPLICIT_DEMO_MODE.strip().lower() == "true"
else:
    DEMO_MODE = not ENV_FILE_PRESENT and not _HAS_REAL_SERVICE_CONFIG and not is_hosted_environment()

RAG_ENABLED = os.getenv("RAG_ENABLED", "true").lower() == "true"
DEMO_TIME_TRAVEL = os.getenv("DEMO_TIME_TRAVEL", "false").lower() == "true"
MAX_UPLOAD_MB = float(os.getenv("MAX_UPLOAD_MB", "8"))
# Keep the AI analysis path well below Vercel's 60-second function limit.
WORK_ANALYSIS_TIMEOUT_SECONDS = max(8.0, min(38.0, float(os.getenv("WORK_ANALYSIS_TIMEOUT_SECONDS", "36"))))
MAX_PDF_PAGES = max(1, min(20, int(os.getenv("MAX_PDF_PAGES", "12"))))
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "300"))
RATE_LIMIT_HEAVY_PER_MIN = int(os.getenv("RATE_LIMIT_HEAVY_PER_MIN", "40"))
FRONTEND_ORIGINS = [x.strip().rstrip("/") for x in os.getenv("FRONTEND_ORIGINS", os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")).split(",") if x.strip()]
FRONTEND_ORIGIN = FRONTEND_ORIGINS[0] if FRONTEND_ORIGINS else "http://localhost:3000"


def openrouter_configured() -> bool:
    return AI_ENABLED and not DEMO_MODE and bool(OPENROUTER_API_KEY) and (
        OPENROUTER_MODEL == "openrouter/free" or OPENROUTER_MODEL.endswith(":free")
    )


def gemini_configured() -> bool:
    # The model name is explicitly configurable; use only free-tier-eligible models/accounts.
    return AI_ENABLED and not DEMO_MODE and bool(GEMINI_API_KEY) and GEMINI_MODEL.startswith("gemini-")


def ai_configured() -> bool:
    return openrouter_configured() or gemini_configured()


def supabase_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SECRET_KEY)


def demo_data_enabled() -> bool:
    """Synthetic student records are allowed only in an unconfigured local checkout."""
    if not DEMO_MODE or is_hosted_environment() or ENV_FILE_PRESENT:
        return False
    # Service credentials supplied via the shell/platform also mean real-data mode,
    # even if this checkout has no .env file.
    if SUPABASE_URL or SUPABASE_SECRET_KEY or OPENROUTER_API_KEY or GEMINI_API_KEY:
        return False
    return True
