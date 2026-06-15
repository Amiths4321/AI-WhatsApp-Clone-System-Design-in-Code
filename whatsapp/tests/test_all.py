# tests/test_all.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from colorama import Fore, Style, init
init(autoreset=True)

def ok(m):   print(Fore.GREEN  + f"  ✅ {m}")
def fail(m): print(Fore.RED    + f"  ❌ {m}")
def hdr(m):  print(Fore.CYAN   + f"\n{'='*50}\n  TEST: {m}\n{'='*50}")


def test_security():
    hdr("Core — JWT + Password Hashing")
    from core.security import hash_password, verify_password, create_token, decode_token

    # Password hash/verify
    h = hash_password("mysecret123")
    assert ":" in h, "Hash should contain salt:hash"
    ok(f"Password hashed: {h[:30]}...")

    assert verify_password("mysecret123", h)
    ok("Correct password verified")

    assert not verify_password("wrongpass", h)
    ok("Wrong password rejected")

    # JWT round-trip
    token = create_token(user_id=42)
    assert isinstance(token, str) and len(token) > 20
    ok(f"JWT created: {token[:30]}...")

    uid = decode_token(token)
    assert uid == 42
    ok("JWT decoded correctly → user_id=42")

    # Invalid token
    assert decode_token("not.a.token") is None
    ok("Invalid token returns None")

    # Tampered token
    assert decode_token(token[:-5] + "XXXXX") is None
    ok("Tampered token rejected")


def test_presence():
    hdr("Service — Presence Service")
    import time
    from services.presence_service import PresenceService
    p = PresenceService()

    # Offline by default
    assert not p.is_online(99)
    ok("User offline by default")

    # Heartbeat → online
    p.heartbeat(1)
    assert p.is_online(1)
    ok("User online after heartbeat")

    # Go offline
    p.go_offline(1)
    assert not p.is_online(1)
    ok("User offline after explicit logout")

    # Typing indicator
    p.heartbeat(2)
    p.set_typing(conv_id=5, user_id=2)
    typing = p.get_typing_users(conv_id=5, exclude_user_id=99)
    assert 2 in typing
    ok("Typing indicator set correctly")

    # Typing expires
    from unittest.mock import patch
    import services.presence_service as ps
    with patch.object(ps, 'TYPING_TTL_SECONDS', -1):
        p2 = PresenceService()
        p2.set_typing(5, 3)
        # TTL is -1 so already expired
        typing2 = p2.get_typing_users(5, 99)
        assert 3 not in typing2
    ok("Typing indicator expires correctly")

    # Bulk online check
    p.heartbeat(10); p.heartbeat(11)
    online = p.get_online_users([10, 11, 12])
    assert 10 in online and 11 in online and 12 not in online
    ok(f"Bulk online check: {online}")


def test_message_states():
    hdr("DB — Message State Machine")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from db.database import Base
    from db.repository import (UserRepository, ConversationRepository,
                               MessageRepository, MessageStatusRepository)
    from models.message import MessageState, ConversationType
    from core.security import hash_password

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Create two users
    ur = UserRepository(db)
    alice = ur.create("1111111111", "Alice", hash_password("pass"))
    bob   = ur.create("2222222222", "Bob",   hash_password("pass"))
    ok(f"Users created: Alice(id={alice.id}), Bob(id={bob.id})")

    # Create conversation
    cr = ConversationRepository(db)
    conv = cr.create(ConversationType.DIRECT, alice.id)
    cr.add_member(conv.id, alice.id, is_admin=True)
    cr.add_member(conv.id, bob.id)
    ok(f"Conversation created: id={conv.id}")

    # Alice sends a message
    mr = MessageRepository(db)
    msg = mr.create(conv.id, alice.id, "Hello Bob!")
    ok(f"Message created: id={msg.id}, content='{msg.content}'")

    # Fan-out: create status for Bob (recipient)
    sr = MessageStatusRepository(db)
    sr.create_bulk(msg.id, [bob.id])

    # Initial state = SENT
    state = sr.get_aggregate_state(msg.id, alice.id)
    assert state == MessageState.SENT
    ok(f"Initial state: {state} ✓")

    # Bob receives → DELIVERED
    sr.update_state(msg.id, bob.id, MessageState.DELIVERED)
    state = sr.get_aggregate_state(msg.id, alice.id)
    assert state == MessageState.DELIVERED
    ok(f"After delivery: {state} ✓✓")

    # Bob reads → READ
    sr.update_state(msg.id, bob.id, MessageState.READ)
    state = sr.get_aggregate_state(msg.id, alice.id)
    assert state == MessageState.READ
    ok(f"After read: {state} 🔵")

    db.close()


def test_pagination():
    hdr("DB — Cursor-based Pagination")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from db.database import Base
    from db.repository import (UserRepository, ConversationRepository,
                               MessageRepository)
    from models.message import ConversationType
    from core.security import hash_password

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    ur = UserRepository(db)
    user = ur.create("3333333333", "Carol", hash_password("pass"))
    cr = ConversationRepository(db)
    conv = cr.create(ConversationType.DIRECT, user.id)
    cr.add_member(conv.id, user.id)

    # Insert 25 messages
    mr = MessageRepository(db)
    for i in range(25):
        mr.create(conv.id, user.id, f"Message {i+1}")

    # First page (no cursor) → should get 20 newest
    page1 = mr.get_page(conv.id, before_id=None, page_size=20)
    assert len(page1) == 21  # 20 + 1 to detect has_more
    has_more = len(page1) > 20
    page1 = page1[:20]
    assert has_more
    ok(f"Page 1: {len(page1)} messages, has_more={has_more}")

    # Second page using cursor
    cursor = page1[-1].id
    page2 = mr.get_page(conv.id, before_id=cursor, page_size=20)
    assert len(page2) <= 6  # only 5 remaining (25 - 20)
    ok(f"Page 2: {len(page2)} messages (remaining)")

    # No overlap between pages
    page1_ids = {m.id for m in page1}
    page2_ids = {m.id for m in page2[:5]}
    assert page1_ids.isdisjoint(page2_ids)
    ok("No overlap between pages ✅")

    db.close()


def test_api():
    hdr("API Layer — Full Flow")
    from db.database import create_tables
    create_tables()
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)

    # Health
    r = client.get("/health")
    assert r.status_code == 200
    ok("GET /health → 200")

    # Register two users
    r = client.post("/auth/register", json={
        "phone": "9000000001", "display_name": "Alice", "password": "pass123"
    })
    assert r.status_code == 201
    alice_token = r.json()["access_token"]
    alice_id    = r.json()["user_id"]
    ok(f"Alice registered: id={alice_id}")

    r = client.post("/auth/register", json={
        "phone": "9000000002", "display_name": "Bob", "password": "pass123"
    })
    assert r.status_code == 201
    bob_token = r.json()["access_token"]
    bob_id    = r.json()["user_id"]
    ok(f"Bob registered: id={bob_id}")

    # Duplicate registration → 409
    r = client.post("/auth/register", json={
        "phone": "9000000001", "display_name": "Alice2", "password": "pass123"
    })
    assert r.status_code == 409
    ok("Duplicate phone → 409")

    # Login
    r = client.post("/auth/login", json={"phone": "9000000001", "password": "pass123"})
    assert r.status_code == 200
    ok("Login → 200")

    # Wrong password → 401
    r = client.post("/auth/login", json={"phone": "9000000001", "password": "wrong"})
    assert r.status_code == 401
    ok("Wrong password → 401")

    # Create conversation
    r = client.post("/conversations", json={"type": "direct", "member_ids": [bob_id]},
                    headers={"Authorization": f"Bearer {alice_token}"})
    assert r.status_code == 201
    conv_id = r.json()["id"]
    ok(f"Conversation created: id={conv_id}")

    # Duplicate direct → returns existing
    r = client.post("/conversations", json={"type": "direct", "member_ids": [bob_id]},
                    headers={"Authorization": f"Bearer {alice_token}"})
    assert r.status_code == 201
    assert r.json()["id"] == conv_id
    ok("Duplicate direct chat returns existing conversation")

    # Send message (Alice)
    r = client.post("/messages/send",
                    json={"conversation_id": conv_id, "content": "Hello Bob!"},
                    headers={"Authorization": f"Bearer {alice_token}"})
    assert r.status_code == 201
    msg_id = r.json()["id"]
    state  = r.json()["state"]
    ok(f"Message sent: id={msg_id}, state={state}")

    # Bob heartbeats → online
    client.post("/presence/heartbeat",
                headers={"Authorization": f"Bearer {bob_token}"})

    # Get messages (Bob) → should mark as delivered
    r = client.get(f"/messages/{conv_id}",
                   headers={"Authorization": f"Bearer {bob_token}"})
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert len(msgs) >= 1
    ok(f"Bob gets {len(msgs)} message(s)")

    # Bob marks as read
    r = client.patch("/messages/receipt",
                     json={"message_id": msg_id, "state": "read"},
                     headers={"Authorization": f"Bearer {bob_token}"})
    assert r.status_code == 204
    ok("Bob marks message as READ → 204")

    # Unauthorized access → 401
    r = client.post("/messages/send",
                    json={"conversation_id": conv_id, "content": "hack"},
                    headers={"Authorization": "Bearer fake_token"})
    assert r.status_code in (401, 403)
    ok(f"Fake token → {r.status_code}")

    # Typing indicator
    r = client.post(f"/presence/typing/{conv_id}",
                    headers={"Authorization": f"Bearer {alice_token}"})
    assert r.status_code == 204
    ok("Typing indicator set → 204")

    r = client.get(f"/presence/typing/{conv_id}",
                   headers={"Authorization": f"Bearer {bob_token}"})
    assert r.status_code == 200
    ok(f"Bob sees typing: {r.json()}")


if __name__ == "__main__":
    print(Fore.CYAN + "\n🧪 WHATSAPP CLONE — ALL LAYER TESTS")
    tests = [
        ("JWT + Password",   test_security),
        ("Presence Service", test_presence),
        ("Message States",   test_message_states),
        ("Pagination",       test_pagination),
        ("API Endpoints",    test_api),
    ]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn(); passed += 1
        except Exception as e:
            fail(f"FAILED in {name}: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    print(Fore.CYAN + f"\n{'='*50}")
    print(f"  RESULTS: {passed} passed, {failed} failed")
    print(f"{'='*50}" + Style.RESET_ALL)
