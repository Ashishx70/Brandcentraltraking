# Brandcentral TrackShip Configuration Settings
import os

# Secret key for session/token verification
SECRET_KEY = os.environ.get("TRACKSHIP_SECRET_KEY", "brandcentral_secret_key_2026_safe")

# User credentials and role definitions
# Role options: 'admin', 'sale', 'return'
USERS = {
    "admin@brandcentral.in": {
        "password": "Admin@938270",
        "role": "admin",
        "name": "Admin Portal"
    },
    "sale@brandcentral.in": {
        "password": "Sale@123",
        "role": "sale",
        "name": "Sale Department"
    },
    "return@brandcentral.in": {
        "password": "Return@123",
        "role": "return",
        "name": "Return Department"
    }
}

# Concurrency & Worker Limits (Optimized for fast tracking and low memory)
MAX_GLOBAL_DATA_WORKERS = 6       # Fast Track API mode (runs 6 parallel tracking workers)
MAX_GLOBAL_SCREENSHOT_WORKERS = 1 # Playwright Image Mode (strict 1 to protect 512MB RAM)
CHUNK_SIZE = 50                   # Batch chunking to prevent memory ballooning
