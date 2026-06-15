# services/presence_service.py
# ══════════════════════════════════════════════════════
# SERVICE — Presence Tracking
#
# NEW concept: track who is online, typing, last seen
#
# Architecture:
#   - Users send heartbeat every 30s while app is open
#   - If no heartbeat for PRESENCE_TTL (60s) → mark offline
#   - "Typing..." indicator: set for 5s, then expires
#   - In production: Redis with TTL keys (auto-expire)
#   - Here: in-memory dict (same concept, simpler)
# ══════════════════════════════════════════════════════

import time
from typing import Optional, Set
from config.settings import PRESENCE_TTL_SECONDS, TYPING_TTL_SECONDS


class PresenceService:
    """
    ARCHITECTURE ROLE: Real-time user state tracking.

    Real-world: Redis with EXPIRE keys
      SET presence:user:42 "online" EX 60
      SET typing:conv:5:user:42 "1" EX 5

    Here: in-memory dicts with timestamps (same logic)
    """

    def __init__(self):
        # { user_id: last_heartbeat_timestamp }
        self._heartbeats: dict = {}
        # { (conv_id, user_id): typing_until_timestamp }
        self._typing: dict = {}

    # ── HEARTBEAT ─────────────────────────────────────
    def heartbeat(self, user_id: int):
        """
        Client calls this every 30s to say "I'm still here".
        Architecture: this is a high-frequency write —
        In production, batch these into Redis EXPIRE updates.
        """
        self._heartbeats[user_id] = time.time()

    def is_online(self, user_id: int) -> bool:
        """
        User is online if they sent a heartbeat within PRESENCE_TTL.
        Simple but effective — same approach as Discord, Slack.
        """
        last = self._heartbeats.get(user_id)
        if last is None:
            return False
        return (time.time() - last) < PRESENCE_TTL_SECONDS

    def get_online_users(self, user_ids: list) -> Set[int]:
        """Which of these users are currently online?"""
        return {uid for uid in user_ids if self.is_online(uid)}

    def go_offline(self, user_id: int):
        """Explicitly mark user offline (on logout/disconnect)."""
        self._heartbeats.pop(user_id, None)

    # ── TYPING INDICATOR ──────────────────────────────
    def set_typing(self, conv_id: int, user_id: int):
        """
        Mark user as typing in a conversation.
        Auto-expires after TYPING_TTL_SECONDS (5s).
        Architecture: write happens on every keypress —
        debounce client-side to max 1 update/second.
        """
        self._typing[(conv_id, user_id)] = time.time() + TYPING_TTL_SECONDS

    def get_typing_users(self, conv_id: int, exclude_user_id: int) -> list:
        """Who is currently typing in this conversation?"""
        now = time.time()
        typing = []
        expired = []
        for (cid, uid), until in self._typing.items():
            if cid == conv_id and uid != exclude_user_id:
                if now < until:
                    typing.append(uid)
                else:
                    expired.append((cid, uid))
        for key in expired:
            self._typing.pop(key, None)
        return typing


# Singleton — shared across all requests
presence_service = PresenceService()
