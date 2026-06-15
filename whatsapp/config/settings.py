# config/settings.py
# ══════════════════════════════════════════════════════
# PHYSICAL VIEW — Named technology decisions
# New vs URL Shortener: JWT secret, message retention,
# presence TTL, max group size
# ══════════════════════════════════════════════════════

import os
from dotenv import load_dotenv
load_dotenv()

# ── DATABASE ──────────────────────────────────────────
# Dev: SQLite · Prod: Cassandra (write-heavy, time-series msgs)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./whatsapp.db")

# ── AUTH (NEW vs URL shortener) ───────────────────────
# JWT: stateless auth — no session DB needed
# Each token is signed and self-contained
JWT_SECRET      = os.getenv("JWT_SECRET", "dev-secret-change-in-prod")
JWT_ALGORITHM   = "HS256"
JWT_EXPIRE_MINS = int(os.getenv("JWT_EXPIRE_MINS", 60 * 24))  # 24 hours

# ── MESSAGE SETTINGS ──────────────────────────────────
MAX_MESSAGE_LENGTH   = 4096          # chars (WhatsApp limit)
MAX_GROUP_MEMBERS    = 256           # WhatsApp group limit
MESSAGE_PAGE_SIZE    = 20            # messages per page (pagination)
MESSAGE_RETAIN_DAYS  = 30            # delete old messages after 30 days

# ── PRESENCE (NEW) ────────────────────────────────────
# How long before we consider a user "offline"
# User sends heartbeat every 30s → if no heartbeat for 60s = offline
PRESENCE_TTL_SECONDS = int(os.getenv("PRESENCE_TTL", 60))
TYPING_TTL_SECONDS   = 5   # "User is typing..." disappears after 5s

# ── RATE LIMITING ─────────────────────────────────────
RATE_LIMIT_MESSAGES_PER_MIN = 60   # max 60 msgs/min per user

# ── APP ───────────────────────────────────────────────
APP_TITLE   = "WhatsApp Clone API"
APP_VERSION = "1.0.0"
DEBUG       = os.getenv("DEBUG", "true").lower() == "true"
