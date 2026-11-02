"""Test harness configuration.

Source tests explicitly enable the development-only license bypass. Packaged
applications ignore this environment variable.
"""

import os


os.environ.setdefault("TAOBAO_MARKET_DEV_LICENSE_BYPASS", "1")

