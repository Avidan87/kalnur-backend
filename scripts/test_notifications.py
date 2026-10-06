"""
Notification System Integration Test
=====================================
Tests the full push notification workflow:
  1. VAPID key endpoint is reachable
  2. Push subscription save/get/delete DB operations
  3. Scheduler job functions (meal reminders, streak alerts, daily summaries,
     coaching nudges, milestone notifications)
  4. send_push() with a fake subscription (verifies VAPID key is set)
  5. Dead-endpoint cleanup (_dead_endpoints list + _cleanup_dead_endpoints)

Run from the KAI project root:
    python -m scripts.test_notifications
or:
    python scripts/test_notifications.py

Requires a valid .env with VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, and Supabase
credentials. The script uses a real test user from the DB — pass one as an
env var or hardcode a known test user ID below.
"""

import asyncio
import os
import sys
from datetime import datetime

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from kai.database import (
    save_push_subscription,
    get_push_subscriptions,
    get_all_subscriptions,
    delete_push_subscription,
    get_supabase,
)
from kai.jobs.push_scheduler import (
    send_push,
    send_meal_reminders,
    send_streak_alerts,
    send_daily_summaries,
    send_coaching_nudges,
    send_milestone_notifications,
    VAPID_PRIVATE_KEY,
    VAPID_PUBLIC_KEY,
    _dead_endpoints,
    _cleanup_dead_endpoints,
)

# ── Config ────────────────────────────────────────────────────────────────────
# Override with TEST_USER_ID env var or set directly here
TEST_USER_ID = os.getenv("TEST_USER_ID", "")

# Fake subscription — not a real browser sub, will fail with 404/410 from push service
# This tests the error-handling path
FAKE_SUBSCRIPTION = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/fake-test-endpoint-for-kalnur-test",
    "keys": {
        "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtLEqZgbXFnkqDkXnMbT72Pl9tqZGHWXeQjsAg4Lk7FaEb3vS3V_sGR2kSg6Xw",
        "auth": "tBHItJI5svbpez7KI4CCXg",
    },
}

# ── Test helpers ──────────────────────────────────────────────────────────────
PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
SKIP = "\033[93m[SKIP]\033[0m"
INFO = "\033[94m[INFO]\033[0m"

results: list[tuple[str, bool, str]] = []


def log(name: str, passed: bool, detail: str = "") -> None:
    status = PASS if passed else FAIL
    print(f"  {status} {name}" + (f" — {detail}" if detail else ""))
    results.append((name, passed, detail))


def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ── Individual tests ──────────────────────────────────────────────────────────

def test_vapid_keys_set() -> None:
    section("1. VAPID Keys Configuration")
    log("VAPID_PRIVATE_KEY is set",  bool(VAPID_PRIVATE_KEY), f"length={len(VAPID_PRIVATE_KEY)}")
    log("VAPID_PUBLIC_KEY is set",   bool(VAPID_PUBLIC_KEY),  f"length={len(VAPID_PUBLIC_KEY)}")


def test_send_push_with_fake_sub() -> None:
    section("2. send_push() with Fake Subscription")
    if not VAPID_PRIVATE_KEY:
        log("send_push skipped — no VAPID key", True, "SKIP: VAPID_PRIVATE_KEY not set")
        return

    # send_push returns False for invalid endpoints (404/410 expected)
    result = send_push(
        subscription=FAKE_SUBSCRIPTION,
        title="Kalnur Test",
        body="This is a test notification.",
        url="/",
    )
    # We expect False (fake endpoint) — the important thing is it doesn't crash
    log("send_push does not crash on fake sub", True)
    log("Fake endpoint queued in _dead_endpoints", FAKE_SUBSCRIPTION["endpoint"] in _dead_endpoints,
        f"_dead_endpoints={_dead_endpoints}")


async def test_push_db_operations() -> None:
    section("3. Push Subscription DB Operations")

    if not TEST_USER_ID:
        print(f"  {SKIP} TEST_USER_ID not set — skipping DB tests")
        print(f"  {INFO} Set the TEST_USER_ID env var to a real user_id from Supabase")
        results.append(("DB operations (save/get/delete)", False, "SKIP: TEST_USER_ID not set"))
        return

    # 3a. Save
    try:
        await save_push_subscription(TEST_USER_ID, FAKE_SUBSCRIPTION)
        log("save_push_subscription upserts without error", True)
    except Exception as e:
        log("save_push_subscription", False, str(e))
        return

    # 3b. Get
    try:
        subs = await get_push_subscriptions(TEST_USER_ID)
        found = any(s.get("endpoint") == FAKE_SUBSCRIPTION["endpoint"] for s in subs)
        log("get_push_subscriptions returns saved sub", found, f"count={len(subs)}")
    except Exception as e:
        log("get_push_subscriptions", False, str(e))

    # 3c. get_all_subscriptions
    try:
        all_subs = await get_all_subscriptions()
        found_all = any(
            row.get("subscription_json", {}).get("endpoint") == FAKE_SUBSCRIPTION["endpoint"]
            for row in all_subs
        )
        log("get_all_subscriptions includes test user", found_all, f"total_rows={len(all_subs)}")
    except Exception as e:
        log("get_all_subscriptions", False, str(e))

    # 3d. Delete
    try:
        await delete_push_subscription(FAKE_SUBSCRIPTION["endpoint"])
        subs_after = await get_push_subscriptions(TEST_USER_ID)
        deleted = not any(s.get("endpoint") == FAKE_SUBSCRIPTION["endpoint"] for s in subs_after)
        log("delete_push_subscription removes the entry", deleted, f"remaining={len(subs_after)}")
    except Exception as e:
        log("delete_push_subscription", False, str(e))


async def test_cleanup_dead_endpoints() -> None:
    section("4. Dead Endpoint Cleanup")

    if not TEST_USER_ID:
        print(f"  {SKIP} TEST_USER_ID not set — skipping cleanup test")
        results.append(("_cleanup_dead_endpoints", False, "SKIP: TEST_USER_ID not set"))
        return

    # Save a temp subscription, then simulate it going dead
    await save_push_subscription(TEST_USER_ID, FAKE_SUBSCRIPTION)
    _dead_endpoints.append(FAKE_SUBSCRIPTION["endpoint"])
    log("Fake endpoint added to _dead_endpoints", FAKE_SUBSCRIPTION["endpoint"] in _dead_endpoints)

    try:
        await _cleanup_dead_endpoints()
        log("_cleanup_dead_endpoints runs without error", True)
        log("_dead_endpoints cleared after cleanup", len(_dead_endpoints) == 0, f"remaining={_dead_endpoints}")

        # Confirm it's gone from DB
        subs = await get_push_subscriptions(TEST_USER_ID)
        gone = not any(s.get("endpoint") == FAKE_SUBSCRIPTION["endpoint"] for s in subs)
        log("Dead endpoint removed from DB", gone)
    except Exception as e:
        log("_cleanup_dead_endpoints", False, str(e))


async def test_scheduler_job_functions() -> None:
    section("5. Scheduler Job Functions (dry run — no real subs needed)")

    # We test that the functions run without crashing even if there are no subscribers.
    # All notification sends will be no-ops if _dead_endpoints are cleaned or VAPID is missing.

    for name, coro in [
        ("send_meal_reminders",  send_meal_reminders()),
        ("send_streak_alerts",   send_streak_alerts()),
        ("send_daily_summaries", send_daily_summaries()),
        ("send_coaching_nudges", send_coaching_nudges()),
    ]:
        try:
            await coro
            log(f"{name}() runs without exception", True)
        except Exception as e:
            log(f"{name}()", False, f"{type(e).__name__}: {e}")


async def test_milestone_notifications() -> None:
    section("6. Milestone Notifications")

    if not TEST_USER_ID:
        print(f"  {SKIP} TEST_USER_ID not set — skipping milestone test")
        results.append(("send_milestone_notifications", False, "SKIP: TEST_USER_ID not set"))
        return

    try:
        await send_milestone_notifications(TEST_USER_ID)
        log("send_milestone_notifications() runs without exception", True,
            "(no push sent if no milestone threshold met)")
    except Exception as e:
        log("send_milestone_notifications", False, f"{type(e).__name__}: {e}")


def test_supabase_reachable() -> None:
    section("7. Supabase Connectivity")
    try:
        client = get_supabase()
        # A lightweight read — just check the connection works
        result = client.table("push_subscriptions").select("user_id").limit(1).execute()
        log("Supabase connection reachable", True, f"rows_returned={len(result.data or [])}")
    except Exception as e:
        log("Supabase connection", False, f"{type(e).__name__}: {e}")


def test_frontend_contract() -> None:
    """
    Validates that the backend push endpoints exist as expected by the frontend:
      GET  /api/v1/push/vapid-public-key  -> { public_key: string }
      POST /api/v1/push/subscribe         -> { success: bool, message: str }
      DELETE /api/v1/push/subscribe       -> { success: bool, message: str }

    This is a static check of server.py imports — no HTTP call needed.
    """
    section("8. Frontend <-> Backend Contract (static)")
    try:
        from kai.api.server import app
        # Build a map of path -> set of methods (FastAPI stores methods as sets)
        route_map: dict[str, set[str]] = {}
        for r in app.routes:
            path = getattr(r, "path", None)
            methods = getattr(r, "methods", None)
            if path and methods:
                route_map.setdefault(path, set()).update(methods)

        checks = [
            ("GET  /api/v1/push/vapid-public-key", "/api/v1/push/vapid-public-key", "GET"),
            ("POST /api/v1/push/subscribe",        "/api/v1/push/subscribe",        "POST"),
            ("DELETE /api/v1/push/subscribe",      "/api/v1/push/subscribe",        "DELETE"),
        ]
        for label, path, method in checks:
            exists = method in route_map.get(path, set())
            log(f"Route {label} registered", exists)
    except Exception as e:
        log("API route inspection", False, str(e))


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary() -> None:
    section("SUMMARY")
    passed  = sum(1 for _, ok, d in results if ok and not d.startswith("SKIP"))
    failed  = sum(1 for _, ok, _ in results if not ok)
    skipped = sum(1 for _, ok, d in results if ok and d.startswith("SKIP"))
    total   = len(results)

    print(f"  Total : {total}")
    print(f"  Passed: \033[92m{passed}\033[0m")
    print(f"  Failed: \033[91m{failed}\033[0m")
    print(f"  Skipped: \033[93m{skipped}\033[0m")

    if failed:
        print("\n  Failed tests:")
        for name, ok, detail in results:
            if not ok:
                print(f"    - {name}: {detail}")

    print()
    return failed


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> int:
    print("\n" + "=" * 60)
    print("  Kalnur Notification System — Integration Test")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if TEST_USER_ID:
        print(f"\n  {INFO} Using TEST_USER_ID: {TEST_USER_ID}")
    else:
        print(f"\n  {SKIP} TEST_USER_ID not set — DB/milestone tests will be skipped")
        print(f"  {INFO} Set: export TEST_USER_ID=<a real user_id from Supabase>")

    test_vapid_keys_set()
    test_supabase_reachable()
    test_frontend_contract()
    test_send_push_with_fake_sub()
    await test_push_db_operations()
    await test_cleanup_dead_endpoints()
    await test_scheduler_job_functions()
    await test_milestone_notifications()

    failed = print_summary()
    return 1 if failed else 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
