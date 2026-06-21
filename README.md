# Pizzasale API

A microservices-based backend for a pizza restaurant ecommerce platform, built with **FastAPI**, **PostgreSQL**, and **RabbitMQ**.

Users can register, verify their email, and authenticate securely. A new registration triggers an asynchronous, event-driven workflow that creates a user profile in a separate service. Profiles can then be read and updated through a JWT-protected API — no service calls another service's API to create data, and no service touches another's database.

---

## Architecture

This project follows three complementary patterns:

**1. Database-per-service** — each microservice owns its own PostgreSQL database and is the only service allowed to read/write it directly.

**2. Event-driven communication** — services don't call each other's APIs synchronously to propagate side effects. Instead, a service publishes an event when something happens, and any number of other services can independently react to it, without the publisher knowing or caring who's listening.

**3. Shared-secret JWT verification across services** — `auth-service` issues JWTs; `user-service` independently verifies them using the same signing secret, without ever calling back into `auth-service`. Each service trusts the token's signature, not a network round-trip.

```text
┌──────────────┐                                    ┌──────────────┐
│ auth-service │                                    │ user-service │
│  (FastAPI)   │                                    │  (FastAPI)   │
└──────┬───────┘                                    └──────┬───────┘
       │                                                    │
       │ on register:                                       │ GET/PATCH /users/{user_id}
       │ publish "user.registered"                           │ (JWT-protected, self-only)
       ▼                                                    │
┌─────────────────────────┐                                │
│   RabbitMQ               │                                │
│   exchange: user_events  │                                │
│   (topic)                │                                │
└────────────┬─────────────┘                                │
             │ routing key: user.registered                 │
             ▼                                               │
┌────────────────────────────┐                              │
│ user-service-worker         │──────────────────────────────┘
│ (separate container,        │  writes profile row
│  same image as user-service,│  (idempotent — UNIQUE
│  different entrypoint)      │   constraint on user_id)
└────────────┬─────────────────┘
             ▼
┌──────────────────┐
│  user_service_db  │
└──────────────────┘

┌──────────────────┐
│  auth_service_db  │   ← owned exclusively by auth-service
└──────────────────┘

        \____________  ____________/
                     \/
       single local PostgreSQL instance
       (separate databases — host-managed,
        outside Docker Compose)
```

**Why event-driven instead of a direct API call?** A direct call (`auth-service` → `POST user-service/users`) would couple the two services' uptime together — if `user-service` is down or slow, registration breaks too, even though registration itself succeeded. Publishing an event instead means `auth-service` doesn't wait on anyone; `user-service` consumes the event whenever it's able to, and the same event can later be consumed by other services (e.g. a future `notification-service`) without ever touching `auth-service`'s code.

**Why a separate worker container, not a background task inside the API?** Running the consumer as its own process means the API and the event-processing workload can be deployed, restarted, and scaled independently — a slow consumer doesn't affect API latency, and an API redeploy doesn't interrupt event processing.

**At-least-once delivery, handled idempotently.** RabbitMQ can redeliver a message more than once (consumer crash mid-process, network blip). `user-service-worker` doesn't assume each event arrives exactly once — `user_profiles.user_id` has a `UNIQUE` constraint, and a duplicate `user.registered` event is caught and safely ignored rather than creating a duplicate row.

**Why verify JWTs independently instead of calling back to `auth-service`?** A `user-service` request that had to call `auth-service` to validate every token would reintroduce the exact synchronous coupling the event-driven design was meant to avoid. Both services share `JWT_SECRET`, so `user-service` validates a token's signature and claims locally — no network call, no shared point of failure.

**Authorization, not just authentication.** A valid JWT proves *who* the caller is — it doesn't by itself mean they're allowed to access a given profile. `user-service` checks that the authenticated username (from the token) matches the profile being requested, and returns `403` otherwise. This is enforced independently on both `GET` and `PATCH`, and has been tested against both an unrelated user and a self/target `user_id` mismatch.

---

## Services

| Service | Status | Port | Responsibility |
|---|---|---|---|
| `auth-service` | **Done** | `8001` | Registration, strict password validation, email verification (AWS SES), login, JWT issue/refresh, publishes `user.registered` |
| `user-service` | **Done** | `8002` | JWT-protected `GET`/`PATCH /users/{user_id}`, self-only authorization |
| `user-service-worker` | **Done** | — (no HTTP port) | Consumes `user.registered` events, creates profile rows idempotently |
| `product-service` | Not started | — | Pizza menu, pricing, inventory |
| `order-service` | Not started | — | Cart, checkout, order lifecycle |
| `payment-service` | Not started | — | Payment processing, charge confirmation |
| `shipping-service` | Not started | — | Delivery tracking |

---

## Tech Stack

- **Framework:** FastAPI (async)
- **Database:** PostgreSQL, accessed via SQLAlchemy (async, `asyncpg` driver)
- **Migrations:** Alembic — run as an explicit, decoupled step, not automatically on container boot (see below)
- **Message broker:** RabbitMQ (topic exchange, durable queues, manual ack)
- **Auth:** JWT (access + refresh tokens) via `fastapi_jwt_auth2`, verified independently in both `auth-service` and `user-service` via a shared secret
- **Email:** AWS SES (`boto3`)
- **Password hashing:** Werkzeug security helpers
- **Containerization:** Docker + Docker Compose, BuildKit cache mounts for fast rebuilds

---

## Local Development Setup

This project simulates a production-like topology. PostgreSQL is host-managed infrastructure, outside Docker Compose entirely — app containers connect out to it. RabbitMQ, by contrast, runs containerized inside Compose, since message brokers are commonly run this way even in real deployments.

### 1. PostgreSQL (host machine, not containerized)

```bash
sudo -u postgres psql -c "CREATE USER microservices WITH PASSWORD '<password>';"
sudo -u postgres psql -c "CREATE DATABASE auth_service_db OWNER microservices;"
sudo -u postgres psql -c "CREATE DATABASE user_service_db OWNER microservices;"
```

`postgresql.conf` needs `listen_addresses = '*'`. `pg_hba.conf` needs a rule allowing the **full Docker private address range**, not just one subnet — Compose creates a different bridge subnet per project, so scope broadly:

```
host    all             all             172.16.0.0/12            scram-sha-256
```

Restart PostgreSQL after changing either file.

### 2. Environment variables

Copy `.env.example` to `.env` (not committed) and fill in real values — Postgres credentials, RabbitMQ credentials, JWT secret, AWS SES credentials and verified sender email. `JWT_SECRET` must be identical across `auth-service` and `user-service` — it's how `user-service` verifies tokens it never issued.

### 3. Run everything

```bash
docker compose up -d --build
```

This starts: RabbitMQ, `auth-service`, `user-service` (API), and `user-service-worker` (consumer).

### 4. Run migrations (explicit step, not automatic)

Migrations are intentionally **not** run on container boot — that pattern breaks down with multiple replicas, since they'd all race to migrate simultaneously on deploy. Run them explicitly, once:

```bash
docker compose exec auth-service alembic upgrade head
docker compose exec user-service alembic upgrade head
```

Whenever a model changes:

```bash
docker compose exec <service> alembic revision --autogenerate -m "describe the change"
# review the generated file before applying
docker compose exec <service> alembic upgrade head
```

### 5. Verify

```bash
curl http://localhost:8001/docs
curl http://localhost:8002/docs
```

Register a user (must be a real, SES-verified address while SES is in sandbox mode):

```bash
curl -X POST http://localhost:8001/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"you@example.com","password":"TestPass123!"}'
```

Check your inbox, click the verification link, then confirm a profile was created on the other side of the event pipeline:

```bash
sudo -u postgres psql -d user_service_db -c "SELECT * FROM user_profiles;"
```

Log in to get a token, then fetch and update the profile:

```bash
curl -X POST http://localhost:8001/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"TestPass123!"}'

curl http://localhost:8002/users/<user_id> \
  -H "Authorization: Bearer <access_token>"

curl -X PATCH http://localhost:8002/users/<user_id> \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"full_name": "Your Name"}'
```

The RabbitMQ management UI (`http://localhost:15672`) is useful for watching this happen live — the **Exchanges → user_events** page shows a publish spike on each registration, and **Queues → user_service.user_registered** shows the consumer picking it up.

---

## Project Structure

```text
.
├── auth-service/
│   ├── alembic/
│   ├── app/
│   │   ├── api/                # Route handlers
│   │   ├── core/                # Security helpers
│   │   ├── db/                  # Engine/session setup
│   │   ├── models/               # SQLAlchemy models
│   │   ├── schemas/              # Pydantic request/response models, password validation
│   │   ├── services/              # Business logic (register, authenticate, activate)
│   │   └── utils/                 # SES email sending, verification tokens, RabbitMQ publisher
│   ├── Dockerfile
│   └── start.sh
├── user-service/
│   ├── alembic/
│   ├── app/
│   │   ├── api/                # GET/PATCH /users/{user_id}, self-only authorization
│   │   ├── core/                 # JWT verification config (shared secret with auth-service)
│   │   ├── db/
│   │   ├── models/                # UserProfile (unique user_id constraint)
│   │   ├── schemas/                # Read/partial-update request and response models
│   │   ├── services/                # Profile fetch, partial update, idempotent event-driven creation
│   │   ├── workers/                   # RabbitMQ consumer — separate entrypoint from the API
│   │   └── main.py                    # FastAPI app
│   ├── Dockerfile
│   └── start.sh
├── docker-compose.yml            # rabbitmq, auth-service, user-service, user-service-worker
└── .env                          # not committed
```

---

## Roadmap

- [x] `auth-service`: registration, strict password validation, login, JWT issue/refresh
- [x] `auth-service`: real email verification via AWS SES, login gated on verification
- [x] Event-driven communication: `auth-service` publishes, `user-service-worker` consumes
- [x] Idempotent, at-least-once event consumption (proven under real failure conditions, not just designed for it)
- [x] `user-service`: JWT-protected profile read/update endpoints, self-only authorization (proven against both an unrelated user and a self/target mismatch)
- [ ] `product-service`: menu browsing
- [ ] `order-service`: cart and checkout
- [ ] `payment-service`: payment processing
- [ ] `shipping-service`: delivery tracking
- [ ] API gateway / service-to-service auth
- [ ] SES production access (currently sandbox — verified recipients only)
- [ ] Embed `user_id` directly in JWT claims (currently `user-service` matches on username, since that's what `auth-service` puts in the token subject — works correctly, but a `user_id` claim would be more direct)

---

## Why This Project Exists

Built as a hands-on backend engineering project to practice production-relevant patterns: async Python, JWT auth and cross-service token verification, database-per-service architecture, event-driven service communication via RabbitMQ, and containerized local dev that mirrors how a real deployment would be wired — rather than a single-database CRUD tutorial. Several real production failure modes were deliberately worked through rather than avoided, including Postgres network/auth configuration across shifting Docker subnets, Docker layer-cache and BuildKit tuning, consumer idempotency under genuine message redelivery, and authorization boundaries verified with actual cross-user requests rather than assumed correct by inspection.