#!/usr/bin/env python3
"""Checks for the part of ftdata.py that decides *not* to fetch.

This exists because of a specific week. In September 2026 the city renamed its
open data portal, the old host began answering every query carrying a `$select`
with a bare nginx 403, and `sf311-day` failed 591 times over seven days -- four
times an hour, every hour, each attempt a faithful repeat of a request that had
no chance of working. The wall drew a real, complete, seven-day-old day the
whole time, because a failed fetch deliberately leaves the previous record in
place, and nothing anywhere said a word.

Two things came out of that, and this file is what keeps them honest:

  1. **A 4xx must back off, and a 5xx must not.** The distinction is the whole
     point and it is easy to lose: a timeout and a 403 arrive at the same
     `except` clause, and treating them alike in either direction is a bug. Back
     off on everything and a source that blipped for one tick is dark for six
     hours; back off on nothing and we are here again.
  2. **Somebody must be told.** The backoff makes a broken product quieter,
     which is exactly what let this hide -- so the alert is not a nicety
     bolted on beside it, it is the other half of the same change. The
     threshold, the repeat interval and the recovery message are all asserted
     here, against a webhook this file stands up itself.

Nothing in here talks to the internet. The failures are synthetic, the webhook
is an http.server on loopback, and every product is a stub registered into the
registry for the length of one test.

    $ python3 scripts/test-ftdata-backoff.py
"""

import email.message
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.error

from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import ftdata                                                 # noqa: E402

FAILED = []
PASSED = [0]


def check(name, ok, detail=""):
    PASSED[0] += 1
    if ok:
        print("  ok   %-58s %s" % (name, detail))
    else:
        print("  FAIL %-58s %s" % (name, detail))
        FAILED.append(name)


def section(title):
    print("\n%s" % title)


# --------------------------------------------------------------------------
# Scaffolding
# --------------------------------------------------------------------------

def http_error(code, retry_after=None):
    """A urllib HTTPError exactly as a product's fetch would raise it."""
    hdrs = email.message.Message()
    if retry_after is not None:
        hdrs["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("https://example.invalid/x", code,
                                  "Forbidden", hdrs, None)


class Stub(object):
    """A product registered for the length of a `with`."""

    def __init__(self, name, raises=None, interval=None, ttl=3600):
        self.name, self.raises, self.interval, self.ttl = \
            name, raises, interval, ttl
        self.calls = 0

    def __enter__(self):
        def fn():
            self.calls += 1
            if self.raises is not None:
                raise self.raises
            return {"value": self.calls}, "stub://%s" % self.name
        # The whole registry is swapped out, not added to: a test that calls
        # fetch_all() with no filter would otherwise fetch all thirty-odd real
        # products off the actual internet, which is both slow and rude.
        self.saved = ftdata.PRODUCTS.copy()
        ftdata.PRODUCTS.clear()
        ftdata.PRODUCTS[self.name] = {
            "fn": fn, "ttl": self.ttl, "description": "stub",
            "interval": self.interval, "volatile": False}
        return self

    def __exit__(self, *exc):
        ftdata.PRODUCTS.clear()
        ftdata.PRODUCTS.update(self.saved)


class Webhook(object):
    """A Slack-shaped endpoint on loopback that remembers what it was sent."""

    def __init__(self, status=200):
        self.posts = []
        self.status = status
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):                                # noqa: N802
                n = int(self.headers.get("Content-Length") or 0)
                outer.posts.append(json.loads(self.rfile.read(n) or b"{}"))
                self.send_response(outer.status)
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d/hook" % self.server.server_port

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        os.environ[ftdata.SLACK_WEBHOOK_ENV] = self.url
        return self

    def __exit__(self, *exc):
        os.environ.pop(ftdata.SLACK_WEBHOOK_ENV, None)
        self.server.shutdown()
        self.server.server_close()


class Cache(object):
    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="ftdata-backoff-")
        return self.dir

    def __exit__(self, *exc):
        shutil.rmtree(self.dir, ignore_errors=True)


# --------------------------------------------------------------------------

def test_classification():
    section("what counts as a 4xx")
    check("a 403 is an HTTP status", ftdata.http_status(http_error(403)) == 403)
    check("a 500 is an HTTP status", ftdata.http_status(http_error(500)) == 500)
    for exc in (ValueError("no rows"), OSError("timed out"),
                json.JSONDecodeError("x", "y", 0)):
        check("%s is not an HTTP status" % type(exc).__name__,
              ftdata.http_status(exc) is None)


def test_delay_curve():
    section("how long the wait is")
    base, cap = ftdata.BACKOFF_BASE, ftdata.BACKOFF_MAX
    check("the first wait is one base interval",
          ftdata.backoff_delay(1) == base, "%ds" % base)
    check("it doubles", ftdata.backoff_delay(2) == base * 2 and
          ftdata.backoff_delay(3) == base * 4)
    check("it is capped", ftdata.backoff_delay(40) == cap, "%ds" % cap)
    check("it never drops below the product's own cadence",
          ftdata.backoff_delay(1, interval=cap * 2) == cap * 2)
    check("a Retry-After can only make it longer",
          ftdata.backoff_delay(1, retry_after=base * 3) == base * 3 and
          ftdata.backoff_delay(1, retry_after=1) == base)
    # The incident, as arithmetic: 96 attempts a day became this many.
    day, t, n = 86400.0, 0.0, 0
    while t < day:
        n += 1
        t += ftdata.backoff_delay(n)
    check("a permanently-broken product is tried a handful of times a day",
          n <= 8, "%d attempts in 24h, was 96" % n)


def test_4xx_defers_5xx_does_not():
    section("a 4xx backs off, a 5xx keeps trying")
    with Cache() as c:
        with Stub("stub-403", raises=http_error(403)) as s:
            ftdata.fetch("stub-403", c)
            check("a 403 defers the next attempt",
                  ftdata.defer_seconds("stub-403", c) > 0,
                  "in %s" % ftdata.describe_age(
                      ftdata.defer_seconds("stub-403", c)))
            n, seen, deferred = ftdata.fetch_all(c, None, False, None)
            check("...and fetch_all skips it while it waits",
                  s.calls == 1 and [d[0] for d in deferred] == ["stub-403"])
            check("...and counts it as considered, not as refreshed",
                  seen == 1 and n == 0)
            check("...and names it in the summary line",
                  "stub-403" in ftdata._deferred_phrase(deferred, c) and
                  "403" in ftdata._deferred_phrase(deferred, c),
                  ftdata._deferred_phrase(deferred, c).strip(", "))
        with Stub("stub-500", raises=http_error(500)) as s:
            ftdata.fetch("stub-500", c)
            check("a 500 does not defer anything",
                  ftdata.defer_seconds("stub-500", c) == 0)
            ftdata.fetch_all(c, None, False, None)
            check("...so it is tried again on the very next pass",
                  s.calls == 2, "%d calls" % s.calls)
        with Stub("stub-slow", raises=OSError("timed out")) as s:
            ftdata.fetch("stub-slow", c)
            ftdata.fetch_all(c, None, False, None)
            check("nor does a timeout", s.calls == 2, "%d calls" % s.calls)


def test_explicit_only_overrides():
    section("--only always tries")
    with Cache() as c:
        with Stub("stub-403", raises=http_error(403)) as s:
            ftdata.fetch("stub-403", c)
            ftdata.fetch_all(c, {"stub-403"}, False, None)
            check("a named product is fetched even while backed off",
                  s.calls == 2, "%d calls" % s.calls)


def test_counting_and_recovery():
    section("counting, and clearing")
    with Cache() as c:
        with Stub("stub-x", raises=http_error(404)) as s:
            for _ in range(3):
                ftdata.note_failure("stub-x", http_error(404), c)
            got = ftdata.load_failures(c)["stub-x"]
            check("consecutive failures are counted", got["count"] == 3)
            check("the status is kept", got["status"] == 404)
            check("the first failure's time is kept", got["first"] <= got["last"])
            s.raises = None
            ftdata.fetch("stub-x", c)
            check("one success clears the whole entry",
                  "stub-x" not in ftdata.load_failures(c))
            check("...and the record is written", ftdata.load("stub-x", c) is not None)


def test_state_is_durable_and_safe():
    section("the state file")
    with Cache() as c:
        ftdata.note_failure("stub-y", http_error(403), c)
        path = ftdata._fail_path(c)
        check("it lands in the cache, where a reboot cannot clear it",
              os.path.exists(path))
        check("it is hidden, so it is not mistaken for a product record",
              os.path.basename(path).startswith("."))
        open(path, "w").write("{not json")
        check("a corrupt file reads as 'nothing is failing'",
              ftdata.load_failures(c) == {})
        check("...and does not raise on the next write",
              ftdata.note_failure("stub-y", http_error(403), c) is None)


def test_alerting():
    section("saying so")
    with Cache() as c, Webhook() as hook:
        with Stub("stub-z", raises=http_error(403)):
            for i in range(1, ftdata.ALERT_AFTER):
                ftdata.fetch("stub-z", c)
                check("nothing is sent after %d failure(s)" % i,
                      hook.posts == [])
            ftdata.fetch("stub-z", c)
            check("an alert goes out at the threshold",
                  len(hook.posts) == 1, "after %d" % ftdata.ALERT_AFTER)
            text = hook.posts[0].get("text", "")
            check("it is Slack-shaped", list(hook.posts[0]) == ["text"])
            check("it names the product", "stub-z" in text)
            check("it gives the status", "403" in text)
            check("it says which wall", ftdata.HOSTNAME in text)
            check("it says when the next attempt is", "next try" in text)
            ftdata.fetch("stub-z", c)
            ftdata.fetch("stub-z", c)
            check("it does not repeat while it is still broken",
                  len(hook.posts) == 1, "%d posts" % len(hook.posts))
        with Stub("stub-z"):
            ftdata.fetch("stub-z", c)
            check("recovery is announced", len(hook.posts) == 2)
            check("...and says so", "again" in hook.posts[1]["text"])
            check("...and is not the failure colour",
                  "\U0001f534" not in hook.posts[1]["text"])


def test_alert_repeat_window():
    section("a source that stays down")
    with Cache() as c, Webhook() as hook:
        with Stub("stub-w", raises=http_error(403)):
            for _ in range(ftdata.ALERT_AFTER):
                ftdata.fetch("stub-w", c)
            check("one alert so far", len(hook.posts) == 1)
            state = ftdata.load_failures(c)
            state["stub-w"]["alerted"] -= ftdata.ALERT_REPEAT + 1
            state["stub-w"]["until"] = 0
            ftdata._save_failures(state, c)
            ftdata.fetch("stub-w", c)
            check("it speaks up again once the repeat window passes",
                  len(hook.posts) == 2, "every %s"
                  % ftdata.describe_age(ftdata.ALERT_REPEAT))


def test_alerting_is_optional_and_harmless():
    section("when the webhook is unset or broken")
    with Cache() as c:
        os.environ.pop(ftdata.SLACK_WEBHOOK_ENV, None)
        with Stub("stub-q", raises=http_error(403)) as s:
            for _ in range(ftdata.ALERT_AFTER):
                ok = ftdata.fetch("stub-q", c)
            check("an unset webhook is not an error", ok is False and
                  ftdata.load_failures(c)["stub-q"]["count"] == ftdata.ALERT_AFTER)
            check("...and nothing claims to have alerted",
                  not ftdata.load_failures(c)["stub-q"]["alerted"])
        # A webhook that refuses connections must not take the fetcher with it.
        os.environ[ftdata.SLACK_WEBHOOK_ENV] = "http://127.0.0.1:1/hook"
        try:
            with Stub("stub-r", raises=http_error(403)):
                for _ in range(ftdata.ALERT_AFTER):
                    ftdata.fetch("stub-r", c)
                check("a dead webhook does not break the fetch",
                      ftdata.load_failures(c)["stub-r"]["count"]
                      == ftdata.ALERT_AFTER)
                check("...and it will try to alert again rather than give up",
                      not ftdata.load_failures(c)["stub-r"]["alerted"])
            with Stub("stub-s"):
                check("a successful fetch still succeeds",
                      ftdata.fetch("stub-s", c) is True)
        finally:
            os.environ.pop(ftdata.SLACK_WEBHOOK_ENV, None)


def test_the_incident():
    section("the September 2026 incident, replayed")
    with Cache() as c, Webhook() as hook:
        with Stub("sf311-like", raises=http_error(403), interval=3600) as s:
            # A week of timer ticks, four an hour, exactly as it happened. The
            # clock is virtual: note_failure() stamps `until` against the real
            # time.time(), so after each attempt the deadline is rewritten to
            # sit the same distance into the *simulated* future. Without that
            # the week takes a week.
            now = time.time()
            for tick in range(7 * 24 * 4):
                when = now + tick * 900.0
                if ftdata.defer_seconds("sf311-like", c, now=when) > 0:
                    continue
                ftdata.fetch("sf311-like", c)
                state = ftdata.load_failures(c)
                got = state.get("sf311-like")
                if got:
                    got["until"] = when + ftdata.backoff_delay(
                        got["count"], ftdata.interval_for("sf311-like"))
                    ftdata._save_failures(state, c)
            check("672 ticks no longer mean 672 requests",
                  s.calls < 60, "%d attempts over the week, was 591" % s.calls)
            check("...which is a few tries a day, not four an hour",
                  s.calls / 7.0 < 9, "%.1f a day" % (s.calls / 7.0))
            check("and somebody was told, on the first day",
                  len(hook.posts) >= 1, "%d alerts" % len(hook.posts))


def main():
    test_classification()
    test_delay_curve()
    test_4xx_defers_5xx_does_not()
    test_explicit_only_overrides()
    test_counting_and_recovery()
    test_state_is_durable_and_safe()
    test_alerting()
    test_alert_repeat_window()
    test_alerting_is_optional_and_harmless()
    test_the_incident()

    print("\n%d checks, %d failed" % (PASSED[0], len(FAILED)))
    for name in FAILED:
        print("  - %s" % name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
