# Pizzasale API

A microservices-based backend for a pizza restaurant ecommerce platform, built with **FastAPI** and **PostgreSQL**.

Users will be able to register, authenticate securely, browse the menu, check out, pay, and track order/shipping status. This repo is being built incrementally, starting with the authentication service.

---

## Architecture

This project follows a **database-per-service** pattern: each microservice owns its own PostgreSQL database and is the only service allowed to read/write it directly. Services never reach into another service's tables — they talk to each other through APIs (and later, events) instead.

```text
┌─────────────────┐         ┌─────────────────┐
│   auth-service   │         │   user-service   │
│   (FastAPI)      │         │   (FastAPI)      │
└────────┬─────────┘         └────────┬─────────┘
         │                            │
         ▼                            ▼
┌──────────────────┐       ┌──────────────────┐
│  auth_service_db  │       │  user_service_db  │
└──────────────────┘       └──────────────────┘
         \____________  ____________/
                      \/
        single local PostgreSQL instance
           (separate databases, not
            a shared schema)
```

Both databases currently live on one PostgreSQL instance for local-dev simplicity — that's an operational choice, not a violation of the per-service-ownership principle. They could be split onto separate instances later without changing any application code, since each service only ever sees its own `DATABASE_URL`.

**Why not a shared database?** A shared database between services creates hidden coupling — a schema change in one service can silently break another. Keeping each service's data isolated forces communication through explicit APIs/events, which is what actually makes services independently deployable.

---

## Services

| Service | Status | Port | Responsibility |
|---|---|---|---|
| `auth-service` | In progress | `8001` | User registration, login, JWT issuance |
| `user-service` | Scaffolded, not implemented | `8002` | User profile data |
| `product-service` | Not started | — | Pizza menu, pricing, inventory |
| `order-service` | Not started | — | Cart, checkout, order lifecycle |
| `payment-service` | Not started | — | Payment processing, charge confirmation |
| `shipping-service` | Not started | — | Delivery tracking |

---

## Tech Stack

- **Framework:** FastAPI (async)
- **Database:** PostgreSQL, accessed via SQLAlchemy (async, `asyncpg` driver)
- **Migrations:** Alembic
- **Auth:** JWT (access + refresh tokens) via `fastapi_jwt_auth2`
- **Password hashing:** Werkzeug security helpers
- **Containerization:** Docker + Docker Compose

---

## Local Development Setup

This project simulates a production-like topology: app containers are stateless and disposable, while PostgreSQL runs as a persistent service **outside** Docker Compose — on the host machine, not in a container.

### 1. PostgreSQL (host machine, not containerized)

Local PostgreSQL must be running and configured to accept connections from Docker's bridge network:

```bash
sudo -u postgres psql -c "CREATE USER microservices WITH PASSWORD '<password>';"
sudo -u postgres psql -c "CREATE DATABASE auth_service_db OWNER microservices;"
sudo -u postgres psql -c "CREATE DATABASE user_service_db OWNER microservices;"
```

`postgresql.conf` needs `listen_addresses = '*'`, and `pg_hba.conf` needs a rule allowing the Docker bridge subnet (default `172.17.0.0/16`) to connect with password auth. Restart PostgreSQL after changing either file.

### 2. Environment variables

Copy `.env.example` to `.env` (not committed — see `.gitignore`) and fill in real values. Connection strings point at `host.docker.internal`, which each container resolves to the host machine via `extra_hosts` in `docker-compose.yml`.

### 3. Run the services

```bash
docker compose up -d --build
docker compose logs -f auth-service
```

Migrations run automatically on container start (see `auth-service/start.sh`), so the schema is created/updated before the API starts serving requests.

### 4. Verify

```bash
curl http://localhost:8001/docs
```

```bash
curl -X POST http://localhost:8001/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"testpass123"}'
```

---

## Project Structure

```text
.
├── auth-service/
│   ├── alembic/              # Migration scripts
│   ├── app/
│   │   ├── api/               # Route handlers
│   │   ├── core/              # Config, security helpers
│   │   ├── db/                # Engine/session setup
│   │   ├── models/             # SQLAlchemy models
│   │   ├── schemas/            # Pydantic request/response models
│   │   └── services/            # Business logic
│   ├── Dockerfile
│   └── start.sh
├── user-service/             # Scaffolded, not yet implemented
├── docker-compose.yml
└── .env                       # Not committed
```

---

## Roadmap

- [x] `auth-service`: registration, login, JWT issuance
- [ ] `user-service`: profile management
- [ ] `product-service`: menu browsing
- [ ] `order-service`: cart and checkout
- [ ] `payment-service`: payment processing
- [ ] `shipping-service`: delivery tracking
- [ ] API gateway / service-to-service auth
- [ ] Event-driven communication between services (e.g. order placed → payment requested)

---

## Why This Project Exists

Built as a hands-on backend engineering project to practice production-relevant patterns — async Python, JWT auth, database-per-service architecture, and containerized local dev that mirrors how a real deployment would be wired — rather than a single-database CRUD tutorial.