# Pizzasale API

A microservices-based backend for a pizza restaurant ecommerce platform, built with **FastAPI**, **PostgreSQL**, and **RabbitMQ**.

Users can register, verify their email, and authenticate securely. A new registration triggers an asynchronous, event-driven workflow that creates a user profile in a separate service. Profiles can be read and updated through a JWT-protected API. A separate catalog service exposes a public, browsable menu — categories and products with size-based pricing — while keeping all writes restricted to staff accounts. No service calls another service's API to create data, and no service touches another's database.

---

## Architecture

This project follows four complementary patterns:

**1. Database-per-service** — each microservice owns its own PostgreSQL database and is the only service allowed to read/write it directly.

**2. Event-driven communication** — services don't call each other's APIs synchronously to propagate side effects. Instead, a service publishes an event when something happens, and any number of other services can independently react to it, without the publisher knowing or caring who's listening.

**3. Shared-secret JWT verification across services** — `auth-service` issues JWTs; `user-service` and `product-service` independently verify them using the same signing secret, without ever calling back into `auth-service`. Each service trusts the token's signature, not a network round-trip.

**4. Public reads, claim-gated writes** — `product-service`'s menu is openly browsable by anyone, but creating, updating, or deleting catalog data requires a JWT carrying `is_staff: true`. Authentication (who you are) and authorization (what you're allowed to do) are enforced as two distinct, separately-tested checks.

```text
┌──────────────┐      ┌──────────────┐      ┌────────────────────┐
│ auth-service │      │ user-service │      │ product-service    │
│  (FastAPI)   │      │  (FastAPI)   │      │  (FastAPI)         │
└──────┬───────┘      └──────┬───────┘      └──────────┬─────────┘
       │                     │                         │
       │ on register:        │ GET/PATCH               │ GET (public):
       │ publish             │ /users/{user_id}        │ categories, products
       │ "user.registered"   │ (JWT, self-only)        │ POST/PATCH/DELETE
       ▼                     │                         │ (JWT, is_staff only)
┌─────────────────────────┐  │                         │
│   RabbitMQ              │  │                         │
│   exchange: user_events │  │                         │
│   (topic)               │  │                         │
└─────────┬───────────────┘  │                         │
          │ routing key:     │                         │
          │ user.registered  │                         │
          ▼                  ▼                         │
┌─────────────────────────────┐                        │
│ user-service-worker         │                        │
│ (separate container,        │                        │
│  same image as user-service,│                        │
│  different entrypoint)      │                        │
└────────────┬────────────────┘                        │
             │                                         │
             ▼                                         ▼
┌──────────────────┐  ┌──────────────────┐  ┌─────────────────────┐
│  auth_service_db │  │  user_service_db │  │  product_service_db │
└──────────────────┘  └──────────────────┘  └─────────────────────┘
        \____________________  ____________________/
                              \/
              single local PostgreSQL instance
           (separate databases — host-managed,
                outside Docker Compose)
```

**Why event-driven instead of a direct API call?** A direct call (`auth-service` → `POST user-service/users`) would couple the two services' uptime together — if `user-service` is down or slow, registration breaks too, even though registration itself succeeded. Publishing an event instead means `auth-service` doesn't wait on anyone; `user-service` consumes the event whenever it's able to, and the same event can later be consumed by other services (e.g. a future `notification-service`) without ever touching `auth-service`'s code.

**Why a separate worker container, not a background task inside the API?** Running the consumer as its own process means the API and the event-processing workload can be deployed, restarted, and scaled independently — a slow consumer doesn't affect API latency, and an API redeploy doesn't interrupt event processing.

**At-least-once delivery, handled idempotently.** RabbitMQ can redeliver a message more than once (consumer crash mid-process, network blip). `user-service-worker` doesn't assume each event arrives exactly once — `user_profiles.user_id` has a `UNIQUE` constraint, and a duplicate `user.registered` event is caught and safely ignored rather than creating a duplicate row.

**Why verify JWTs independently instead of calling back to `auth-service`?** A request that had to call `auth-service` to validate every token would reintroduce the exact synchronous coupling the event-driven design was meant to avoid. Every service that needs to verify identity shares `JWT_SECRET` and validates a token's signature and claims locally — no network call, no shared point of failure. Each service also registers a handler for `AuthJWTException` so a missing or invalid token returns a clean `401`/`403` with a real error body, not an unhandled `500`.

**Authorization, not just authentication.** A valid JWT proves *who* the caller is — it doesn't by itself mean they're allowed to do something. `user-service` checks that the authenticated username matches the profile being requested (self-only access, `403` otherwise). `product-service` checks the token's `is_staff` claim before allowing any write, while leaving every read endpoint completely public. Both boundaries have been tested against real failing cases — an unrelated user's token, a missing token, a non-staff token — not just assumed correct by inspection.

**Why a relational catalog (categories → products → variants) instead of one flat table?** A flat `category` string column on `products` means renaming a category is a bulk text update with real risk of inconsistent spelling across rows. A real `categories` table makes renaming, reordering, and deactivating a category a single-row change. Size-based pricing is modeled as its own `product_variants` table (one row per size/price pair) rather than fixed price columns on `products`, so adding a new size or temporarily 86'ing just the "large" of one product doesn't require a schema change. Prices are stored as `Numeric(10,2)`, not `Float` — `Float` introduces real floating-point rounding error for currency values.

---

## Services

| Service | Status | Port | Responsibility |
|---|---|---|---|
| `auth-service` | **Done** | `8001` | Registration, strict password validation, email verification (AWS SES), login, JWT issue/refresh, publishes `user.registered` |
| `user-service` | **Done** | `8002` | JWT-protected `GET`/`PATCH /users/{user_id}`, self-only authorization |
| `user-service-worker` | **Done** | — (no HTTP port) | Consumes `user.registered` events, creates profile rows idempotently |
| `product-service` | **Done** | `8003` | Public menu browsing (categories, products, size-based pricing); staff-only create/update/delete |
| `order-service` | Not started | — | Cart, checkout, order lifecycle |
| `payment-service` | Not started | — | Payment processing, charge confirmation |
| `shipping-service` | Not started | — | Delivery tracking |

---

## Tech Stack

- **Framework:** FastAPI (async)
- **Database:** PostgreSQL, accessed via SQLAlchemy (async, `asyncpg` driver)
- **Migrations:** Alembic — run as an explicit, decoupled step, not automatically on container boot (see below)
- **Message broker:** RabbitMQ (topic exchange, durable queues, manual ack)
- **Auth:** JWT (access + refresh tokens) via `fastapi_jwt_auth2`, verified independently in every service that needs it, via a shared secret
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
sudo -u postgres psql -c "CREATE DATABASE product_service_db OWNER microservices;"
```

`postgresql.conf` needs `listen_addresses = '*'`. `pg_hba.conf` needs a rule allowing the **full Docker private address range**, not just one subnet — Compose creates a different bridge subnet per project, so scope broadly:

```
host    all             all             172.16.0.0/12            scram-sha-256
```

Restart PostgreSQL after changing either file.

### 2. Environment variables

Copy `.env.example` to `.env` (not committed) and fill in real values — Postgres credentials, RabbitMQ credentials, JWT secret, AWS SES credentials and verified sender email. `JWT_SECRET` must be identical across every service — it's how each one verifies tokens it never issued.

### 3. Run everything

```bash
docker compose up -d --build
```

This starts: RabbitMQ, `auth-service`, `user-service` (API), `user-service-worker` (consumer), and `product-service`.

### 4. Run migrations (explicit step, not automatic)

Migrations are intentionally **not** run on container boot — that pattern breaks down with multiple replicas, since they'd all race to migrate simultaneously on deploy. Run them explicitly, once:

```bash
docker compose exec auth-service alembic upgrade head
docker compose exec user-service alembic upgrade head
docker compose exec product-service alembic upgrade head
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
curl http://localhost:8003/docs
```

Register a user (must be a real, SES-verified address while SES is in sandbox mode), verify via the emailed link, then log in:

```bash
curl -X POST http://localhost:8001/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"you@example.com","password":"TestPass123!"}'

TOKEN=$(curl -s -X POST http://localhost:8001/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"TestPass123!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access'])")
```

Confirm the profile was created on the other side of the event pipeline:

```bash
curl http://localhost:8002/users/<user_id> -H "Authorization: Bearer $TOKEN"
```

Browse the public menu (no token needed):

```bash
curl http://localhost:8003/products
```

To create catalog data, a user needs `is_staff = true` (set manually for now — there's no admin-promotion endpoint yet):

```bash
sudo -u postgres psql -d auth_service_db -c "UPDATE users_auth SET is_staff = true WHERE username = 'testuser';"
# log in again — is_staff is baked into the token at login time
```

The RabbitMQ management UI (`http://localhost:15672`) is useful for watching the event flow live — the **Exchanges → user_events** page shows a publish spike on each registration, and **Queues → user_service.user_registered** shows the consumer picking it up.

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
├── product-service/
│   ├── alembic/
│   ├── app/
│   │   ├── api/                # Category and product routes — public reads, staff-only writes
│   │   ├── core/                 # JWT verification, require_staff dependency
│   │   ├── db/
│   │   ├── models/                # Category, Product, ProductVariant (size/price pairs)
│   │   ├── schemas/                # Create/update/response shapes, nested variant validation
│   │   ├── services/                # Category and product CRUD, eager-loaded variant queries
│   │   └── main.py                    # FastAPI app
│   ├── Dockerfile
│   └── start.sh
├── docker-compose.yml            # rabbitmq, auth-service, user-service, user-service-worker, product-service
└── .env                          # not committed
```

---

## Roadmap

- [x] `auth-service`: registration, strict password validation, login, JWT issue/refresh
- [x] `auth-service`: real email verification via AWS SES, login gated on verification
- [x] Event-driven communication: `auth-service` publishes, `user-service-worker` consumes
- [x] Idempotent, at-least-once event consumption (proven under real failure conditions, not just designed for it)
- [x] `user-service`: JWT-protected profile read/update endpoints, self-only authorization (proven against both an unrelated user and a self/target mismatch)
- [x] `product-service`: relational catalog (categories, products, size-based variants), public reads, staff-only writes (proven against missing-token and non-staff cases)
- [x] Consistent `AuthJWTException` handling across all services — clean `401`/`403` responses instead of unhandled `500`s on missing/invalid tokens
- [ ] `order-service`: cart and checkout
- [ ] `payment-service`: payment processing
- [ ] `shipping-service`: delivery tracking
- [ ] API gateway / service-to-service auth
- [ ] SES production access (currently sandbox — verified recipients only)
- [ ] Admin/staff-promotion flow (currently `is_staff` is only settable by hand in Postgres)
- [ ] Embed `user_id` directly in JWT claims (currently `user-service` matches on username, since that's what `auth-service` puts in the token subject — works correctly, but a `user_id` claim would be more direct)
- [ ] Automated integration test suite covering the full cross-service flow (currently verified manually, end to end)

---

## Why This Project Exists

Built as a hands-on backend engineering project to practice production-relevant patterns: async Python, JWT auth and cross-service token verification, database-per-service architecture, event-driven service communication via RabbitMQ, relational data modeling for a real domain, and containerized local dev that mirrors how a real deployment would be wired — rather than a single-database CRUD tutorial. Several real production failure modes were deliberately worked through rather than avoided, including Postgres network/auth configuration across shifting Docker subnets, Docker layer-cache and BuildKit tuning, consumer idempotency under genuine message redelivery, an unhandled-exception gap in JWT error handling caught by testing the unhappy path rather than assuming it worked, and authorization boundaries verified with actual cross-user and cross-permission requests rather than assumed correct by inspection.