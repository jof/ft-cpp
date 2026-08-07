#!/usr/bin/env python3
"""Minimal control-socket client: ftc.py <command...>

Everything answers in text except `snapshot`, which answers with a header and
then raw pixels. That one is turned into a P6 PPM on stdout, with the header
echoed to stderr, so it can go straight into a file or a viewer:

  python3 ftc.py snapshot > wall.ppm
  python3 ftc.py snapshot | display -            # ImageMagick
"""
import socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(3)
s.connect("/run/ft/control.sock")
s.sendall((" ".join(sys.argv[1:]) + "\n").encode())
out = b""
while True:
    c = s.recv(65536)
    if not c: break
    out += c

head, sep, body = out.partition(b"\n\n")
if sep and head.startswith(b"snapshot "):
    # snapshot rgb24 <width> <height> <bytes>
    fields = head.split(b"\n", 1)[0].split()
    width, height, count = fields[2], fields[3], int(fields[4])
    sys.stderr.write(head.decode("ascii", "replace") + "\n")
    sys.stdout.buffer.write(b"P6\n" + width + b" " + height + b"\n255\n")
    sys.stdout.buffer.write(body[:count])
else:
    sys.stdout.write(out.decode("ascii", "replace"))
