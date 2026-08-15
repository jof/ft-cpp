#!/usr/bin/env python3
"""Check /api/live.png: one encode, many viewers, and nothing when unwatched.

A sibling of test-snapshot.py rather than part of it, because it needs no
server: the broadcaster's whole job is what it does with frames, so the wall
here is a variable this file sets. That keeps it runnable on a laptop with
nothing built, which is where it will actually get run.

What is worth asserting is the three properties the stream is built around, and
none of them are about the picture:

  the same bytes reach every viewer, so a second viewer is not a second deflate
  an unchanged wall sends nothing, so watching a blanked wall is free
  no viewers means no work at all, which is a wall's normal condition

Raw sockets rather than http.client throughout: this response has no
Content-Length and ends only when the connection does, which http.client is
within its rights to buffer in ways that make a streaming test lie.

  python3 test-live-stream.py
"""

import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "demos"))
import ftctl                                            # noqa: E402

W, H = 320, 64
FPS = 20

failures = []


def check(label, got, want):
    ok = got == want
    if not ok:
        failures.append(label)
    print("  %-44s %-14s %s %s" % (label, got, "==" if ok else "!=", want))


class FakeControl(object):
    """The wall, as a variable. Counts reads so idleness can be asserted."""

    def __init__(self):
        self.pixels = bytes(W * H * 3)
        self.reads = 0

    def snapshot(self):
        self.reads += 1
        return {"width": W, "height": H, "blanked": False, "brightness": 80,
                "generation": 1, "at": time.time(), "pixels": self.pixels}


class FakeBridge(object):
    def __init__(self):
        self.control = FakeControl()

    def snapshot(self):
        return {"display": None, "scheduler": None}


def solid(value):
    return bytes([value]) * (W * H * 3)


class Viewer(object):
    """One streaming client, reading in a thread so several can overlap."""

    def __init__(self, port, method="GET"):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=10)
        self.sock.sendall(("%s /api/live.png HTTP/1.1\r\nHost: t\r\n\r\n"
                           % method).encode())
        self.raw = b""
        self.status = None
        self.headers = None
        self._stop = False
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        while not self._stop:
            try:
                chunk = self.sock.recv(65536)
            except (socket.timeout, OSError):
                return
            if not chunk:
                return
            self.raw += chunk
            if self.status is None and b"\r\n\r\n" in self.raw:
                head = self.raw.split(b"\r\n\r\n", 1)[0].decode("latin-1")
                self.status = int(head.split()[1])
                self.headers = head

    def frames(self):
        """The PNG payloads seen so far, parsed out of the multipart stream."""
        out = []
        buf = self.raw
        marker = b"--" + ftctl.LIVE_BOUNDARY.encode()
        i = buf.find(marker)
        while i >= 0:
            j = buf.find(b"\r\n\r\n", i)
            if j < 0:
                break
            head = buf[i:j].decode("latin-1")
            k = head.find("Content-Length: ")
            if k < 0:
                break
            length = int(head[k + 16:].split("\r\n")[0])
            body = buf[j + 4:j + 4 + length]
            if len(body) < length:
                break
            out.append(body)
            i = buf.find(marker, j + 4 + length)
        return out

    def close(self):
        # shutdown() before close(): this thread's reader is sitting in recv(),
        # and closing under it neither wakes it nor reliably puts a FIN on the
        # wire until it returns -- which would make the server look slow to
        # notice a departure that had not actually happened yet.
        self._stop = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


def settle(seconds=0.4):
    time.sleep(seconds)


def main():
    bridge = FakeBridge()
    wall = bridge.control
    srv = ftctl.Server(("127.0.0.1", 0), bridge, "/nonexistent",
                       live_fps=FPS, live_max_viewers=2)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    settle(0.3)

    try:
        # -- one encode, two viewers -------------------------------------
        wall.pixels = solid(10)
        a, b = Viewer(port), Viewer(port)
        settle(0.5)
        for value in (60, 120, 180):
            wall.pixels = solid(value)
            settle(0.3)
        fa, fb = a.frames(), b.frames()
        check("viewer A accepted", a.status, 200)
        check("viewer B accepted", b.status, 200)
        check("content type is multipart",
              "multipart/x-mixed-replace; boundary=%s" % ftctl.LIVE_BOUNDARY
              in (a.headers or ""), True)
        check("A saw several frames", len(fa) >= 3, True)
        check("B saw several frames", len(fb) >= 3, True)
        check("every part is a PNG",
              all(f.startswith(b"\x89PNG") for f in fa + fb), True)
        # The point of encoding once: the bytes are literally the same object,
        # so what each viewer wrote must agree wherever the two overlap.
        check("viewers agree byte for byte",
              len(set(fa) & set(fb)) >= 3, True)

        # -- the cap ------------------------------------------------------
        third = Viewer(port)
        settle(0.5)
        check("third viewer refused", third.status, 503)
        check("refusal says when to retry", "Retry-After" in (third.headers or ""),
              True)
        third.close()

        # -- HEAD must not take a slot ------------------------------------
        head = Viewer(port, method="HEAD")
        settle(0.4)
        check("HEAD answered, not streamed", head.status, 200)
        head.close()

        # -- a still wall sends nothing -----------------------------------
        b.close()
        settle(0.5)
        before = len(a.frames())
        reads_before = wall.reads
        settle(1.5)                       # 30 renders at 20 fps, all identical
        check("still wall sends no repeats", len(a.frames()), before)
        check("still wall is still being read",
              wall.reads > reads_before, True)
        wall.pixels = solid(222)
        settle(0.4)
        check("a change sends exactly one frame",
              len(a.frames()), before + 1)

        # -- nothing runs unwatched ---------------------------------------
        # Longer than LIVE_IDLE_PROBE: with the wall standing still, a departed
        # viewer is noticed by the probe write rather than by a frame, so the
        # slot comes back one probe interval after the socket closes.
        a.close()
        settle(ftctl.LIVE_IDLE_PROBE + 1.0)
        idle_at = wall.reads
        settle(1.2)
        check("no reads while unwatched", wall.reads, idle_at)

        # -- and it comes back --------------------------------------------
        c = Viewer(port)
        settle(0.6)
        check("stream restarts for a new viewer", len(c.frames()) >= 1, True)
        c.close()
    finally:
        srv.shutdown()
        srv.server_close()

    print("\n%s" % ("FAIL: " + ", ".join(failures) if failures else "PASS"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
