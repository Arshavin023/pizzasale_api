# Pizzasale API

A microservices-based backend for a pizza restaurant ecommerce platform, built with **FastAPI**, **PostgreSQL**, and **RabbitMQ**.

Users can register, verify their email, and authenticate securely. A new registration triggers an asynchronous, event-driven workflow that creates a user profile in a separate service. Profiles can be read and updated through a JWT-protected API. A separate catalog service exposes a public, browsable menu — categories and products with size-based pricing — while keeping all writes restricted to staff accounts. Users can add items to a persistent cart, check out with real-time price verification, and pay through Paystack's hosted checkout page — with webhook-driven order status updates flowing back through the system automatically. No service touches another's database, and no service calls another's API except where synchronous communication is the correct architectural choice.

---

## Architecture

This project follows four complementary patterns:

**1. Database-per-service** — each microservice owns its own PostgreSQL database and is the only service allowed to read/write it directly.

**2. Event-driven communication** — services don't call each other's APIs synchronously to propagate side effects. Instead, a service publishes an event when something happens, and any number of other services can independently react to it, without the publisher knowing or caring who's listening.

**3. Shared-secret JWT verification across services** — `auth-service` issues JWTs; `user-service` and `product-service` independently verify them using the same signing secret, without ever calling back into `auth-service`. Each service trusts the token's signature, not a network round-trip.

**4. Public reads, claim-gated writes** — `product-service`'s menu is openly browsable by anyone, but creating, updating, or deleting catalog data requires a JWT carrying `is_staff: true`. Authentication (who you are) and authorization (what you're allowed to do) are enforced as two distinct, separately-tested checks.

**5. Synchronous service-to-service calls where correctness requires it** — checkout verifies live prices against `product-service` and initializes payment via `payment-service` synchronously. This is a deliberate exception to the event-driven default: a user sitting at the checkout screen needs an immediate answer, and a failed payment must fail the whole checkout atomically rather than leaving an order in an ambiguous state.

**6. Webhook-driven external integration** — `payment-service` receives Paystack webhooks, verifies every request's HMAC-SHA512 signature before processing, re-verifies the transaction with Paystack's API (never trusting the webhook body alone), then updates the order status and publishes a `payment.succeeded` event — all without any polling or user-initiated confirmation.

```text
┌──────────────┐   ┌──────────────┐   ┌────────────────────┐
│ auth-service │   │ user-service │   │ product-service    │
│  (FastAPI)   │   │  (FastAPI)   │   │  (FastAPI)         │
└──────┬───────┘   └──────┬───────┘   └──────────┬─────────┘
       │                  │                       │
       │ on register:     │ GET/PATCH             │ GET (public)
       │ publish          │ /users/{user_id}      │ POST/PATCH/DELETE
       │ "user.registered"│ (JWT, self-only)      │ (JWT, is_staff only)
       ▼                  │                       │
┌─────────────────────┐   │                       │
│   RabbitMQ          │   │           ┌───────────┴──────────┐
│   user_events       │   │           │   order-service       │
│   order_events      │   │           │   (FastAPI)           │
│   payment_events    │   │           └──────┬────────────────┘
└──────┬──────────────┘   │                  │ sync: verify prices
       │ user.registered  │                  │ → product-service
       ▼                  ▼                  │ sync: initialize payment
┌─────────────────────────┐                  │ → payment-service
│ user-service-worker     │                  │
│ (idempotent consumer)   │                  ▼
└────────────┬────────────┘      ┌───────────────────────┐
             │                   │   payment-service      │
             │                   │   (FastAPI)            │
             │                   │   ← Paystack webhook   │
             │                   │   verifies HMAC-SHA512 │
             │                   │   re-verifies with     │
             │                   │   Paystack API         │
             │                   └──────────┬─────────────┘
             │                              │ publishes payment.succeeded
             ▼                              ▼
┌──────────────────┐  ┌──────────────────┐  ┌─────────────────────┐  ┌──────────────────┐  ┌──────────────────────┐
│  auth_service_db │  │  user_service_db │  │  product_service_db │  │ order_service_db │  │ payment_service_db   │
└──────────────────┘  └──────────────────┘  └─────────────────────┘  └──────────────────┘  └──────────────────────┘
        \____________________________________________  ____________________________________________/
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

**Why synchronous HTTP for checkout price verification and payment, when the rest of the system is event-driven?** This is a deliberate architectural choice, not an inconsistency. The event-driven pattern is correct when a side effect can happen eventually — profile creation, order notifications, payment confirmation emails. Checkout is different: the user is actively waiting for an answer, a stale price could mean charging the wrong amount, and a failed payment must roll back the order immediately. Defaulting to async everywhere regardless of the use case would be as wrong as defaulting to sync everywhere. The system uses each pattern where it fits.

**Why re-verify the Paystack transaction after receiving the webhook, rather than trusting the webhook body?** A webhook endpoint is a public URL — anyone can POST to it. Verifying the HMAC-SHA512 signature proves the request came from Paystack, but the body could still contain stale or replayed data. Re-verifying with Paystack's API (`GET /transaction/verify/{reference}`) confirms the current state of the transaction directly from the source. This is Paystack's documented best practice and prevents a class of attacks where a valid signature is replayed with a modified body.

---

## Services

| Service | Status | Port | Responsibility |
|---|---|---|---|
| `auth-service` | **Done** | `8001` | Registration, strict password validation, email verification (AWS SES), login, JWT issue/refresh, publishes `user.registered` |
| `user-service` | **Done** | `8002` | JWT-protected `GET`/`PATCH /users/{user_id}`, self-only authorization |
| `user-service-worker` | **Done** | — (no HTTP port) | Consumes `user.registered` events, creates profile rows idempotently |
| `product-service` | **Done** | `8003` | Public menu browsing (categories, products, size-based pricing); staff-only create/update/delete |
| `order-service` | **Done** | `8004` | Persistent cart, checkout with live price verification, order lifecycle state machine (`pending_payment → confirmed → paid → shipped → delivered`) |
| `payment-service` | **Done** | `8005` | Paystack initialize+verify flow, HMAC-SHA512 webhook verification, payment audit trail, publishes `payment.succeeded`/`payment.failed` |
| `shipping-service` | Not started | — | Delivery tracking |

---

## Tech Stack

- **Framework:** FastAPI (async)
- **Database:** PostgreSQL, accessed via SQLAlchemy (async, `asyncpg` driver)
- **Migrations:** Alembic — run as an explicit, decoupled step, not automatically on container boot (see below)
- **Message broker:** RabbitMQ (topic exchange, durable queues, manual ack)
- **Auth:** JWT (access + refresh tokens) via `fastapi_jwt_auth2`, verified independently in every service that needs it, via a shared secret
- **Email:** AWS SES (`boto3`)
- **Payments:** Paystack (initialize + verify flow, HMAC-SHA512 webhook signature verification, NGN test mode)
- **Password hashing:** Werkzeug security helpers
- **Containerization:** Docker + Docker Compose, BuildKit cache mounts for fast rebuilds
- **Webhook tunneling (dev):** ngrok — exposes `payment-service` webhook endpoint to Paystack during local development

---

## Local Development Setup

This project simulates a production-like topology. PostgreSQL is host-managed infrastructure, outside Docker Compose entirely — app containers connect out to it. RabbitMQ, by contrast, runs containerized inside Compose, since message brokers are commonly run this way even in real deployments.

### 1. PostgreSQL (host machine, not containerized)

```bash
sudo -u postgres psql -c "CREATE USER microservices WITH PASSWORD '<password>';"
sudo -u postgres psql -c "CREATE DATABASE auth_service_db OWNER microservices;"
sudo -u postgres psql -c "CREATE DATABASE user_service_db OWNER microservices;"
sudo -u postgres psql -c "CREATE DATABASE product_service_db OWNER microservices;"
sudo -u postgres psql -c "CREATE DATABASE order_service_db OWNER microservices;"
sudo -u postgres psql -c "CREATE DATABASE payment_service_db OWNER microservices;"
```

`postgresql.conf` needs `listen_addresses = '*'`. `pg_hba.conf` needs a rule allowing the **full Docker private address range**, not just one subnet — Compose creates a different bridge subnet per project, so scope broadly:

```
host    all             all             172.16.0.0/12            scram-sha-256
```

Restart PostgreSQL after changing either file.

### 2. Environment variables

Copy `.env.example` to `.env` (not committed) and fill in real values — Postgres credentials, RabbitMQ credentials, JWT secret, AWS SES credentials and verified sender email, and Paystack test API keys. `JWT_SECRET` must be identical across every service — it's how each one verifies tokens it never issued.

For local webhook testing, expose `payment-service` via ngrok:

```bash
ngrok http 8005
```

Register the resulting `https://` URL as the webhook URL in your Paystack dashboard (Settings → API Keys & Webhooks → Test Webhook URL), appending `/payments/webhook`.

### 3. Run everything

```bash
docker compose up -d --build
```

This starts: RabbitMQ, `auth-service`, `user-service` (API), `user-service-worker` (consumer), and `product-service`.

### 4. Run migrations (explicit step, not automatic)

Migrations are intentionally **not** run on container boot — that pattern breaks down with multiple replicas, since they'd all race to migrate simultaneously on deploy. Run them explicitly, once:

```bash
docker compose exec auth-service    alembic upgrade head
docker compose exec user-service    alembic upgrade head
docker compose exec product-service alembic upgrade head
docker compose exec order-service   alembic upgrade head
docker compose exec payment-service alembic upgrade head
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
curl http://localhost:8004/docs
curl http://localhost:8005/docs
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
│   │   ├── core/               # Security helpers
│   │   ├── db/                 # Engine/session setup
│   │   ├── models/             # SQLAlchemy models
│   │   ├── schemas/            # Pydantic request/response models, password validation
│   │   ├── services/           # Business logic (register, authenticate, activate)
│   │   └── utils/              # SES email sending, verification tokens, RabbitMQ publisher
│   ├── Dockerfile
│   └── start.sh
├── user-service/
│   ├── alembic/
│   ├── app/
│   │   ├── api/                # GET/PATCH /users/{user_id}, self-only authorization
│   │   ├── core/               # JWT verification config (shared secret with auth-service)
│   │   ├── db/
│   │   ├── models/             # UserProfile (unique user_id constraint)
│   │   ├── schemas/            # Read/partial-update request and response models
│   │   ├── services/           # Profile fetch, partial update, idempotent event-driven creation
│   │   ├── workers/            # RabbitMQ consumer — separate entrypoint from the API
│   │   └── main.py
│   ├── Dockerfile
│   └── start.sh
├── product-service/
│   ├── alembic/
│   ├── app/
│   │   ├── api/                # Category and product routes — public reads, staff-only writes
│   │   ├── core/               # JWT verification, require_staff dependency
│   │   ├── db/
│   │   ├── models/             # Category, Product, ProductVariant (size/price pairs)
│   │   ├── schemas/            # Create/update/response shapes, nested variant validation
│   │   ├── services/           # Category and product CRUD, eager-loaded variant queries
│   │   └── main.py
│   ├── Dockerfile
│   └── start.sh
├── order-service/
│   ├── alembic/
│   ├── app/
│   │   ├── api/                # Cart, checkout, order history endpoints
│   │   ├── core/               # JWT verification, user_id extraction
│   │   ├── db/
│   │   ├── models/             # Cart, CartItem, Order, OrderItem; OrderStatus state machine
│   │   ├── schemas/            # Cart and order request/response shapes
│   │   ├── services/           # CartService, OrderService (checkout flow, price locking)
│   │   └── utils/              # product_client (sync price verify), payment_client, events
│   ├── Dockerfile
│   └── start.sh
├── payment-service/
│   ├── alembic/
│   ├── app/
│   │   ├── api/                # POST /payments/initialize, POST /payments/webhook
│   │   ├── db/
│   │   ├── models/             # Payment (audit trail — every charge attempt recorded)
│   │   ├── schemas/            # Initialize request/response shapes
│   │   ├── services/           # PaymentService (initialize, webhook handling, verify)
│   │   └── utils/              # paystack (API client), webhook (HMAC verification), events, order_client
│   ├── Dockerfile
│   └── start.sh
├── docker-compose.yml
└── .env                        # not committed
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
- [x] `order-service`: persistent cart, checkout with live price verification against `product-service`, order state machine (`draft → pending_payment → confirmed → paid`), `order.placed` event published
- [x] `payment-service`: Paystack initialize+verify flow (test mode, NGN), HMAC-SHA512 webhook signature verification, transaction re-verification with Paystack API, `payment.succeeded`/`payment.failed` events published, order status updated via internal HTTP call
- [x] UUID casting at route layer (Python-side, not relying on PostgreSQL implicit conversion) — consistent across all services, fixes SQLite test compatibility
- [x] Per-service pytest suites running inside containers (226 tests across 4 services)
- [x] Automated E2E test script covering full user journey across all 4 services
- [ ] `payment-service`: tests
- [ ] `shipping-service`: delivery tracking
- [ ] `order-service-worker`: consumes `payment.succeeded` / `shipping.*` events to drive order state transitions beyond `paid`
- [ ] API gateway / service-to-service auth
- [ ] SES production access (currently sandbox — verified recipients only)
- [ ] Admin/staff-promotion endpoint (currently `is_staff` is only settable directly in Postgres)
- [ ] Pass user email to `payment-service` from `user-service` rather than using a hardcoded placeholder

---

## Why This Project Exists

Built as a hands-on backend engineering project to practice production-relevant patterns: async Python, JWT auth and cross-service token verification, database-per-service architecture, event-driven service communication via RabbitMQ, relational data modeling for a real domain, real payment gateway integration (Paystack initialize+verify with webhook signature verification), and containerized local dev that mirrors how a real deployment would be wired — rather than a single-database CRUD tutorial. Several real production failure modes were deliberately worked through rather than avoided, including Postgres network/auth configuration across shifting Docker subnets, Docker layer-cache and BuildKit tuning, consumer idempotency under genuine message redelivery, an unhandled-exception gap in JWT error handling caught by testing the unhappy path rather than assuming it worked, authorization boundaries verified with actual cross-user and cross-permission requests, and the deliberate choice of synchronous vs. asynchronous communication based on the actual requirements of each interaction rather than defaulting to one pattern everywhere.