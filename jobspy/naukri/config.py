import os
from pathlib import Path

LOGIN_URL = os.getenv("NAUKRI_LOGIN_URL", "https://www.naukri.com/nlogin/login")
AUTH_CHECK_URL = os.getenv(
    "NAUKRI_AUTH_CHECK_URL",
    "https://www.naukri.com/mnjuser/homepage",
)
SESSION_BOOTSTRAP_URL = os.getenv(
    "NAUKRI_SESSION_BOOTSTRAP_URL",
    "https://www.naukri.com/software-developer-jobs-in-india",
)
BROWSER = os.getenv("NAUKRI_BROWSER", "chromium").strip().lower()
BROWSER_CHANNEL = os.getenv("NAUKRI_BROWSER_CHANNEL", "").strip() or None

_storage_state_path = Path(
    os.getenv("NAUKRI_STORAGE_STATE_PATH", ".auth/naukri_storage_state.json")
).expanduser()
STORAGE_STATE_PATH = (
    _storage_state_path
    if _storage_state_path.is_absolute()
    else Path.cwd() / _storage_state_path
)
