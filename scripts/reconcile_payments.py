# #!/usr/bin/env python3
# """
# Reconciliation script: detects and fixes inconsistencies between
# payment_service_db and order_service_db.

# This is the safety net for the case where update_order_status() in
# payment-service exhausted its retries and the order was never updated
# to match a confirmed payment outcome. It should never fire in normal
# operation — its job is to catch the rare case where order-service was
# genuinely unreachable for the full retry window.

# USAGE:
#     python3 scripts/reconcile_payments.py             # dry run, just reports
#     python3 scripts/reconcile_payments.py --fix        # actually fixes mismatches
#     python3 scripts/reconcile_payments.py --fix --quiet  # fix silently, exit 0/1 for cron

# RECOMMENDED: run on a schedule (cron, every 5-15 minutes) as a safety net,
# not as the primary mechanism for updating order status. The primary
# mechanism is the synchronous retry-with-backoff call in payment-service's
# order_client.py.

# EXIT CODES:
#     0 — no mismatches found, or all mismatches fixed successfully
#     1 — mismatches found and --fix was not passed (report-only mode found issues)
#     2 — mismatches found and --fix was passed, but one or more fixes failed
# """
# import argparse
# import os
# import sys
# import httpx
# import psycopg2
# import psycopg2.extras

# # Database connection strings — read from environment, falling back to
# # the same credentials used in docker-compose for local dev convenience.
# PAYMENT_DB_URL = os.getenv(
#     "PAYMENT_DATABASE_URL_SYNC",
#     "postgresql://microservices:UcheJudeNnodim3420878321@localhost:5432/payment_service_db",
# )
# ORDER_DB_URL = os.getenv(
#     "ORDER_DATABASE_URL_SYNC",
#     "postgresql://microservices:UcheJudeNnodim3420878321@localhost:5432/order_service_db",
# )
# ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL_LOCAL", "http://localhost:8004")

# # Mapping from payment status to the order status it should produce
# PAYMENT_TO_ORDER_STATUS = {
#     "succeeded": "paid",
#     "failed": "cancelled",
# }


# def fetch_payments(conn):
#     """All payments that reached a terminal state (succeeded/failed)."""
#     with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
#         cur.execute("""
#             SELECT order_id, status, paystack_reference, updated_at
#             FROM payments
#             WHERE status IN ('succeeded', 'failed')
#         """)
#         return cur.fetchall()


# def fetch_order_statuses(conn, order_ids):
#     """Current status for a given list of order IDs."""
#     if not order_ids:
#         return {}
#     with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
#         cur.execute(
#             "SELECT id, status FROM orders WHERE id = ANY(%s)",
#             (order_ids,),
#         )
#         return {str(row["id"]): row["status"] for row in cur.fetchall()}


# def find_mismatches(payments, order_statuses):
#     """
#     Returns a list of dicts describing each payment whose terminal status
#     doesn't match what the corresponding order currently shows.
#     """
#     mismatches = []
#     for payment in payments:
#         order_id = str(payment["order_id"])
#         expected_order_status = PAYMENT_TO_ORDER_STATUS.get(payment["status"])
#         actual_order_status = order_statuses.get(order_id)

#         if actual_order_status is None:
#             mismatches.append({
#                 "order_id": order_id,
#                 "payment_status": payment["status"],
#                 "expected_order_status": expected_order_status,
#                 "actual_order_status": "ORDER NOT FOUND",
#                 "reference": payment["paystack_reference"],
#             })
#         elif actual_order_status != expected_order_status and actual_order_status not in (
#             "shipped", "delivered"
#         ):
#             # Don't flag orders that have already progressed past 'paid' —
#             # shipped/delivered is a legitimate forward state, not a mismatch.
#             mismatches.append({
#                 "order_id": order_id,
#                 "payment_status": payment["status"],
#                 "expected_order_status": expected_order_status,
#                 "actual_order_status": actual_order_status,
#                 "reference": payment["paystack_reference"],
#             })
#     return mismatches


# def fix_mismatch(mismatch: dict, quiet: bool = False) -> bool:
#     """
#     Calls order-service's internal status update endpoint to bring the
#     order in line with the confirmed payment outcome.
#     """
#     order_id = mismatch["order_id"]
#     target_status = mismatch["expected_order_status"]

#     try:
#         resp = httpx.patch(
#             f"{ORDER_SERVICE_URL}/orders/{order_id}/status",
#             json={"status": target_status},
#             timeout=10.0,
#         )
#         if resp.status_code == 200:
#             if not quiet:
#                 print(f"  FIXED: order {order_id} -> {target_status}")
#             return True
#         else:
#             if not quiet:
#                 print(f"  FAILED: order {order_id} -> {target_status} "
#                       f"(order-service returned {resp.status_code})")
#             return False
#     except httpx.RequestError as e:
#         if not quiet:
#             print(f"  FAILED: order {order_id} -> {target_status} (unreachable: {e})")
#         return False


# def main():
#     parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
#     parser.add_argument("--fix", action="store_true", help="Actually apply fixes (default: dry run / report only)")
#     parser.add_argument("--quiet", action="store_true", help="Suppress per-item output, only print summary")
#     args = parser.parse_args()

#     payment_conn = psycopg2.connect(PAYMENT_DB_URL)
#     order_conn = psycopg2.connect(ORDER_DB_URL)

#     try:
#         payments = fetch_payments(payment_conn)
#         order_ids = [str(p["order_id"]) for p in payments]
#         order_statuses = fetch_order_statuses(order_conn, order_ids)

#         mismatches = find_mismatches(payments, order_statuses)

#         if not mismatches:
#             if not args.quiet:
#                 print(f"Reconciliation: checked {len(payments)} terminal payments — no mismatches found.")
#             sys.exit(0)

#         if not args.quiet:
#             print(f"Reconciliation: found {len(mismatches)} mismatch(es) out of {len(payments)} terminal payments:\n")
#             for m in mismatches:
#                 print(f"  order_id={m['order_id']}")
#                 print(f"    payment_status={m['payment_status']} (ref: {m['reference']})")
#                 print(f"    expected order status: {m['expected_order_status']}")
#                 print(f"    actual order status:   {m['actual_order_status']}")
#                 print()

#         if not args.fix:
#             if not args.quiet:
#                 print("Run with --fix to apply corrections.")
#             sys.exit(1)

#         if not args.quiet:
#             print("Applying fixes...\n")

#         all_fixed = True
#         for m in mismatches:
#             success = fix_mismatch(m, quiet=args.quiet)
#             if not success:
#                 all_fixed = False

#         if not args.quiet:
#             if all_fixed:
#                 print(f"\nAll {len(mismatches)} mismatch(es) fixed successfully.")
#             else:
#                 print(f"\nSome mismatches could not be fixed — see FAILED lines above. "
#                       f"Manual investigation required.")

#         sys.exit(0 if all_fixed else 2)

#     finally:
#         payment_conn.close()
#         order_conn.close()


# if __name__ == "__main__":
#     main()

#!/usr/bin/env python3
"""
Reconciliation script: detects and fixes inconsistencies between
payment_service_db and order_service_db.

This is the safety net for the case where update_order_status() in
payment-service exhausted its retries and the order was never updated
to match a confirmed payment outcome. It should never fire in normal
operation — its job is to catch the rare case where order-service was
genuinely unreachable for the full retry window.

USAGE:
    python3 scripts/reconcile_payments.py             # dry run, just reports
    python3 scripts/reconcile_payments.py --fix        # actually fixes mismatches
    python3 scripts/reconcile_payments.py --fix --quiet  # fix silently, exit 0/1 for cron

RECOMMENDED: run on a schedule (cron, every 5-15 minutes) as a safety net,
not as the primary mechanism for updating order status. The primary
mechanism is the synchronous retry-with-backoff call in payment-service's
order_client.py.

EXIT CODES:
    0 — no mismatches found, or all mismatches fixed successfully
    1 — mismatches found and --fix was not passed (report-only mode found issues)
    2 — mismatches found and --fix was passed, but one or more fixes failed
"""
import argparse
import os
import sys
import httpx
import psycopg2
import psycopg2.extras

# Database connection strings — read from environment, falling back to
# the same credentials used in docker-compose for local dev convenience.
PAYMENT_DB_URL = os.getenv(
    "PAYMENT_DATABASE_URL_SYNC",
    "postgresql://microservices:UcheJudeNnodim3420878321@localhost:5432/payment_service_db",
)
ORDER_DB_URL = os.getenv(
    "ORDER_DATABASE_URL_SYNC",
    "postgresql://microservices:UcheJudeNnodim3420878321@localhost:5432/order_service_db",
)
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL_LOCAL", "http://localhost:8004")

# Mapping from payment status to the order status it should produce
PAYMENT_TO_ORDER_STATUS = {
    "succeeded": "paid",
    "failed": "cancelled",
}


def fetch_payments(conn):
    """All payments that reached a terminal state (succeeded/failed)."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT order_id, status, paystack_reference, updated_at
            FROM payments
            WHERE status IN ('succeeded', 'failed')
        """)
        return cur.fetchall()


def fetch_order_statuses(conn, order_ids):
    """Current status for a given list of order IDs."""
    if not order_ids:
        return {}
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT id, status FROM orders WHERE id = ANY(%s::uuid[])",
            (order_ids,),
        )
        return {str(row["id"]): row["status"] for row in cur.fetchall()}


def find_mismatches(payments, order_statuses):
    """
    Returns a list of dicts describing each payment whose terminal status
    doesn't match what the corresponding order currently shows.
    """
    mismatches = []
    for payment in payments:
        order_id = str(payment["order_id"])
        expected_order_status = PAYMENT_TO_ORDER_STATUS.get(payment["status"])
        actual_order_status = order_statuses.get(order_id)

        if actual_order_status is None:
            mismatches.append({
                "order_id": order_id,
                "payment_status": payment["status"],
                "expected_order_status": expected_order_status,
                "actual_order_status": "ORDER NOT FOUND",
                "reference": payment["paystack_reference"],
            })
        elif actual_order_status != expected_order_status and actual_order_status not in (
            "shipped", "delivered"
        ):
            # Don't flag orders that have already progressed past 'paid' —
            # shipped/delivered is a legitimate forward state, not a mismatch.
            mismatches.append({
                "order_id": order_id,
                "payment_status": payment["status"],
                "expected_order_status": expected_order_status,
                "actual_order_status": actual_order_status,
                "reference": payment["paystack_reference"],
            })
    return mismatches


def fix_mismatch(mismatch: dict, quiet: bool = False) -> bool:
    """
    Calls order-service's internal status update endpoint to bring the
    order in line with the confirmed payment outcome.
    """
    order_id = mismatch["order_id"]
    target_status = mismatch["expected_order_status"]

    try:
        resp = httpx.patch(
            f"{ORDER_SERVICE_URL}/orders/{order_id}/status",
            json={"status": target_status},
            timeout=10.0,
        )
        if resp.status_code == 200:
            if not quiet:
                print(f"  FIXED: order {order_id} -> {target_status}")
            return True
        else:
            if not quiet:
                print(f"  FAILED: order {order_id} -> {target_status} "
                      f"(order-service returned {resp.status_code})")
            return False
    except httpx.RequestError as e:
        if not quiet:
            print(f"  FAILED: order {order_id} -> {target_status} (unreachable: {e})")
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fix", action="store_true", help="Actually apply fixes (default: dry run / report only)")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-item output, only print summary")
    args = parser.parse_args()

    payment_conn = psycopg2.connect(PAYMENT_DB_URL)
    order_conn = psycopg2.connect(ORDER_DB_URL)

    try:
        payments = fetch_payments(payment_conn)
        order_ids = [str(p["order_id"]) for p in payments]
        order_statuses = fetch_order_statuses(order_conn, order_ids)

        mismatches = find_mismatches(payments, order_statuses)

        if not mismatches:
            if not args.quiet:
                print(f"Reconciliation: checked {len(payments)} terminal payments — no mismatches found.")
            sys.exit(0)

        if not args.quiet:
            print(f"Reconciliation: found {len(mismatches)} mismatch(es) out of {len(payments)} terminal payments:\n")
            for m in mismatches:
                print(f"  order_id={m['order_id']}")
                print(f"    payment_status={m['payment_status']} (ref: {m['reference']})")
                print(f"    expected order status: {m['expected_order_status']}")
                print(f"    actual order status:   {m['actual_order_status']}")
                print()

        if not args.fix:
            if not args.quiet:
                print("Run with --fix to apply corrections.")
            sys.exit(1)

        if not args.quiet:
            print("Applying fixes...\n")

        all_fixed = True
        for m in mismatches:
            success = fix_mismatch(m, quiet=args.quiet)
            if not success:
                all_fixed = False

        if not args.quiet:
            if all_fixed:
                print(f"\nAll {len(mismatches)} mismatch(es) fixed successfully.")
            else:
                print(f"\nSome mismatches could not be fixed — see FAILED lines above. "
                      f"Manual investigation required.")

        sys.exit(0 if all_fixed else 2)

    finally:
        payment_conn.close()
        order_conn.close()


if __name__ == "__main__":
    main()