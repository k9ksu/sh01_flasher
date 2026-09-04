#!/usr/bin/env python3
"""
Download the stock SH01 v2 firmware (used as the patch base) from the
rcambrj/sovol-dryer-firmware repository into this folder as fw-v2-base.hex.
The hex is Sovol's, so it is not bundled here.
"""
import os
import urllib.request

URL = "https://raw.githubusercontent.com/rcambrj/sovol-dryer-firmware/main/fw-v2.hex"
DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fw-v2-base.hex")

urllib.request.urlretrieve(URL, DEST)
print(f"saved {DEST} ({os.path.getsize(DEST)} bytes)")
