# models/user.py
# ══════════════════════════════════════════════════════
# DATABASE LAYER — User Model
#
# New vs URL Shortener:
#   - Password hashing (never store plain text)
#   - last_seen: presence tracking
#   - is_online: real-time status
# ══════════════════════════════════════════════════════

from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean
from db.database import Base


class User(Base):
    __tablename__ = "users"

    id           = Column(Integer, primary_key=True, index=True)
    phone        = Column(String(20), unique=True, index=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    password_hash = Column(String(256), nullable=False)   # bcrypt hash
    avatar_url   = Column(String(512), nullable=True)

    # ── Presence fields (NEW concept) ─────────────────
    # last_seen: shown as "Last seen today at 3:42 PM"
    # is_online: green dot on profile
    last_seen    = Column(DateTime(timezone=True),
                          default=lambda: datetime.now(timezone.utc))
    is_online    = Column(Boolean, default=False)

    created_at   = Column(DateTime(timezone=True),
                          default=lambda: datetime.now(timezone.utc))
    is_active    = Column(Boolean, default=True)

    def __repr__(self):
        return f"<User {self.phone} ({self.display_name})>"
