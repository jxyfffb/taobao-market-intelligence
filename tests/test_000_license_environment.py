"""Load the explicit source-test license bypass before other test modules."""

import os
import unittest


os.environ["TAOBAO_MARKET_DEV_LICENSE_BYPASS"] = "1"


class LicenseTestEnvironmentTests(unittest.TestCase):
    def test_development_bypass_is_explicit_for_source_tests(self):
        self.assertEqual("1", os.environ["TAOBAO_MARKET_DEV_LICENSE_BYPASS"])

