#!/usr/bin/env python3
"""
Download the stock SH01 v2 firmware (used as the patch base) from the
rcambrj/sovol-dryer-firmware repository into this folder as fw-v2-base.hex.
The hex is Sovol's, so it is not bundled here.

    python get_firmware.py
"""
import hashlib
import os
import urllib.request

URL = "https://raw.githubusercontent.com/rcambrj/sovol-dryer-firmware/main/fw-v2.hex"
DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fw-v2-base.hex")
SHA256 = "48f19f5310733296f7bec79a53382579969b921d1846a1a37d87b07fd79603d3"


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def download(dest: str = DEST) -> str:
    """Fetch the base image, verify its checksum, return the path."""
    tmp = dest + ".part"
    urllib.request.urlretrieve(URL, tmp)
    got = sha256_of(tmp)
    if got != SHA256:
        os.remove(tmp)
        raise RuntimeError(f"checksum mismatch: got {got[:16]}..., expected {SHA256[:16]}...")
    os.replace(tmp, dest)
    return dest


if __name__ == "__main__":
    p = download()
    print(f"saved {p} ({os.path.getsize(p)} bytes, sha256 OK)")
