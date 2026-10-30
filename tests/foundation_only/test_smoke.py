"""Foundation-only smoke test (placeholder).

Per Plan §19.3 (Foundation-Only Viability), the foundation must run with
no domain content. This file is a placeholder until the foundation is
built; it asserts only that the package imports cleanly.
"""

import oaos2


def test_package_imports() -> None:
    assert oaos2.__version__ == "0.0.0"
