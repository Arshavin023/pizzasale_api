# Pizzasale API

A microservices-based backend for a pizza restaurant ecommerce platform, built with **FastAPI**, **PostgreSQL**, and **RabbitMQ**.

Users can register, verify their email, and authenticate securely. A new registration triggers an asynchronous, event-driven workflow that creates a user profile in a separate service — no service calls another service's API directly, and no service touches another's database.

---

## Architecture

This project follows two complementary patterns:

**1. Database-per-service** — each microservice owns its own PostgreSQL database and is the only service allowed to read/write it directly.

**2. Event-driven communication** — services don't call each other's APIs synchronously. Instead, a service publishes an event when something happens, and any number of other services can independently react to it, without the publisher knowing or caring who's listening.

```text
┌──────────────┐                                    ┌──────────────┐
│ auth-service │                                    │ user-service │
│  (FastAPI)   │                                    │  (FastAPI)   │
└──────┬───────┘                                    └──────┬───────┘
       │                                                    │
       │ on register:                                       │ health check,
       │ publish "user.registered"                           │ profile endpoints
       ▼                                                    │ (in progress)
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

---

## Services

| Service | Status | Port | Responsibility |
|---|---|---|---|
| `auth-service` | **Done** | `8001` | Registration, strict password validation, email verification (AWS SES), login, JWT issue/refresh, publishes `user.registered` |
| `user-service` | API scaffolded; profile endpoints not yet built | `8002` | User profile data |
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
- **Auth:** JWT (access + refresh tokens) via `fastapi_jwt_auth2`
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

Copy `.env.example` to `.env` (not committed) and fill in real values — Postgres credentials, RabbitMQ credentials, JWT secret, AWS SES credentials and verified sender email.

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
│   │   ├── db/
│   │   ├── models/                # UserProfile (unique user_id constraint)
│   │   ├── services/                # Idempotent profile creation
│   │   ├── workers/                  # RabbitMQ consumer — separate entrypoint from the API
│   │   └── main.py                   # FastAPI app (health check; more endpoints to come)
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
- [ ] `user-service`: profile read/update endpoints
- [ ] `product-service`: menu browsing
- [ ] `order-service`: cart and checkout
- [ ] `payment-service`: payment processing
- [ ] `shipping-service`: delivery tracking
- [ ] API gateway / service-to-service auth
- [ ] SES production access (currently sandbox — verified recipients only)

---

## Why This Project Exists

Built as a hands-on backend engineering project to practice production-relevant patterns: async Python, JWT auth, database-per-service architecture, event-driven service communication via RabbitMQ, and containerized local dev that mirrors how a real deployment would be wired — rather than a single-database CRUD tutorial. Several real production failure modes were deliberately worked through rather than avoided, including Postgres network/auth configuration across shifting Docker subnets, Docker layer-cache and BuildKit tuning, and consumer idempotency under genuine message redelivery.