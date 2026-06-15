# WhatsApp Clone — System Design in Code
## New concepts vs URL Shortener

```
whatsapp/
│
├── config/settings.py          ← Physical view: named tech choices
│
├── models/                     ← Database layer: 4 tables
│   ├── user.py                 ← Users (auth, presence, last_seen)
│   ├── conversation.py         ← Conversation (group or 1-to-1)
│   └── message.py              ← Message + MessageStatus (NEW: state machine)
│
├── schemas/                    ← API contracts
│   ├── user.py                 ← Register, login, profile
│   ├── conversation.py         ← Create/list conversations
│   └── message.py              ← Send/receive/paginate messages
│
├── db/
│   ├── database.py             ← Engine + session
│   └── repository.py           ← All DB queries (5 repositories)
│
├── core/
│   ├── security.py             ← Password hashing + JWT tokens (NEW)
│   ├── message_state.py        ← SENT→DELIVERED→READ state machine (NEW)
│   └── pagination.py           ← Cursor-based pagination (NEW)
│
├── services/
│   ├── presence_service.py     ← Online/offline/last_seen tracking (NEW)
│   ├── delivery_service.py     ← Fan-out: deliver to all recipients (NEW)
│   └── notification_service.py ← Push when offline (NEW)
│
├── api/routes/
│   ├── auth.py                 ← POST /register, POST /login
│   ├── conversations.py        ← GET/POST /conversations
│   ├── messages.py             ← POST /send, GET /messages, PATCH /receipt
│   └── presence.py             ← GET /online, POST /heartbeat
│
├── tests/test_all.py           ← Test every layer
└── main.py                     ← FastAPI entry point
```

## What this teaches vs URL Shortener

| Concept | URL Shortener | WhatsApp |
|---------|--------------|---------|
| Data model | 1 table | 4 related tables |
| Auth | None | JWT tokens |
| Message states | None | SENT→DELIVERED→READ |
| Fan-out | None | 1 msg → N recipients |
| Presence | None | online/offline/typing |
| Pagination | None | cursor-based |
| Services layer | None | dedicated service classes |

## Run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
# Docs at http://localhost:8000/docs
```
