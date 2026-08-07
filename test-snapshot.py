#!/usr/bin/env python3
"""Check that the control socket's `snapshot` returns the real composite.

Runs a server on the terminal backend, paints two layers with known colours,
and reads the frame back. The interesting part is the layering: `snapshot`
reconstructs what each pixel actually shows from the z-buffer rather than
keeping a fourth buffer, so the test paints an overlay with black (=
transparent) around it and checks the background shows through exactly where it
should.

Blanking is checked only where the backend has a dimmer. The terminal backend
does not, so those two assertions are skipped here rather than failed; the
rgb-matrix backend is where that path is real.

  make -C server && python3 test-snapshot.py
"""

import os
import socket
import subprocess
import sys
import tempfile
import time

W, H = 64, 32
SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "build", "server", "ft-server")

failures = []


def check(label, got, want):
    ok = got == want
    if not ok:
        failures.append(label)
    print("  %-38s %-16s %s %s" % (label, got, "==" if ok else "!=", want))


def send_frame(pixels, layer):
    """The FT protocol: a P6 PPM over UDP, layer in an #FT: header comment."""
    header = b"P6\n#FT: 0 0 %d\n%d %d\n255\n" % (layer, W, H)
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.sendto(header + bytes(pixels), ("127.0.0.1", 1337))
    udp.close()
    time.sleep(0.4)


def talk(path, command):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(3)
    sock.connect(path)
    sock.sendall(command + b"\n")
    out = b""
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        out += chunk
    sock.close()
    return out


def snapshot(path):
    head, _, body = talk(path, b"snapshot").partition(b"\n\n")
    fields = head.split(b"\n", 1)[0].split()
    return (head.decode(), int(fields[2]), int(fields[3]), int(fields[4]), body)


def pixel(buf, x, y):
    i = (y * W + x) * 3
    return (buf[i], buf[i + 1], buf[i + 2])


def main():
    if not os.path.exists(SERVER):
        sys.exit("no %s -- run: make -C server" % SERVER)
    tmp = tempfile.mkdtemp(prefix="ft-snaptest-")
    path = os.path.join(tmp, "control.sock")
    server = subprocess.Popen(
        [SERVER, "-D", "%dx%d" % (W, H), "--control-socket", path,
         "--layer-timeout", "600"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    time.sleep(1.5)
    if server.poll() is not None:
        sys.exit("server died: " + server.stderr.read().decode())

    try:
        background = bytearray(W * H * 3)
        for i in range(0, len(background), 3):
            background[i + 2] = 180                  # solid blue
        send_frame(background, layer=0)

        overlay = bytearray(W * H * 3)               # black => transparent
        for y in range(10, 20):
            for x in range(10, 20):
                overlay[(y * W + x) * 3] = 240       # a red square
        send_frame(overlay, layer=1)

        head, width, height, count, body = snapshot(path)
        print(head)
        check("geometry", (width, height, count), (W, H, W * H * 3))
        check("payload bytes", len(body), W * H * 3)
        check("overlay pixel", pixel(body, 15, 15), (240, 0, 0))
        check("background pixel", pixel(body, 2, 2), (0, 0, 180))
        check("background under transparent overlay",
              pixel(body, 40, 15), (0, 0, 180))
        check("background just outside overlay",
              pixel(body, 9, 15), (0, 0, 180))

        if "dimmer 1" in head:
            talk(path, b"blank on")
            head2, _, _, _, body2 = snapshot(path)
            # Blanking darkens the panel, not the composite: the content has to
            # survive, because it is what comes back when the wall is unblanked.
            check("content survives blanking", pixel(body2, 15, 15), (240, 0, 0))
            check("blanked reported", "blanked 1" in head2, True)
        else:
            print("  (backend has no dimmer: blanking not checked here)")
    finally:
        server.terminate()
        server.wait()
        try:
            os.remove(path)
            os.rmdir(tmp)
        except OSError:
            pass

    print("\n%s" % ("FAIL: " + ", ".join(failures) if failures else "PASS"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
