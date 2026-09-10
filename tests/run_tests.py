"""mayapy test entry point (flat structure).

Run from the project root::

    "C:\\Program Files\\Autodesk\\Maya2024\\bin\\mayapy.exe" tests\\run_tests.py

Use ``-k <substring>`` to run only tests whose name matches::

    mayapy.exe tests\\run_tests.py -k compatibility
"""

from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
#: Flat structure: the parent of tests/ is the project root (core / ui / utils live there)
PROJECT_ROOT = os.path.dirname(HERE)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# support handles initialization centrally so the whole process calls
# standalone.initialize exactly once (initializing twice breaks the current scene).
from tests import support  # noqa: E402

support.ensure_maya()


def main(argv=None) -> int:
    """Discover and run all tests."""
    args = list(sys.argv[1:] if argv is None else argv)
    keyword = None
    if "-k" in args:
        index = args.index("-k")
        if index + 1 < len(args):
            keyword = args[index + 1]
        del args[index:index + 2]

    loader = unittest.TestLoader()
    suite = loader.discover(HERE, pattern="test_*.py", top_level_dir=PROJECT_ROOT)

    if keyword:
        suite = _filter_suite(suite, keyword)
        if suite.countTestCases() == 0:
            print(f"No tests match {keyword!r}")
            return 1

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def _filter_suite(suite: unittest.TestSuite, keyword: str) -> unittest.TestSuite:
    """Filter test cases by substring."""
    filtered = unittest.TestSuite()
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            nested = _filter_suite(test, keyword)
            if nested.countTestCases():
                filtered.addTest(nested)
        elif keyword.lower() in test.id().lower():
            filtered.addTest(test)
    return filtered


if __name__ == "__main__":
    exit_code = main()
    import maya.standalone

    maya.standalone.uninitialize()
    sys.exit(exit_code)
