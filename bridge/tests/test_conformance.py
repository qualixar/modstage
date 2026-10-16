"""Conformance harness: one test per (agent, control) from conformance.py, plus the shared rows.

Gaps are expected failures. When a gap is fixed its test passes unexpectedly and the suite fails:
flip the cell in conformance.py and regenerate docs/PARITY-MATRIX.md (parity_matrix.py).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import conformance as C  # noqa: E402
from fakes import BRIDGE_AGENTS  # noqa: E402


def _make(fn, *args):
    def test(self):
        fn(self, *args)
    return test


class ParityTest(unittest.TestCase):
    pass


for _agent in BRIDGE_AGENTS:
    for _control in C.CONTROLS:
        _state, _why = C.cell(_agent, _control)
        if _state == "n/a" and (_agent, _control) not in C.NA_CHECKED:
            continue
        _test = _make(C.CHECKS[_control], _agent)
        _test.__doc__ = f"{_agent} · {C.TITLES[_control]} · {_state}{': ' + _why if _why else ''}"
        if _state == "gap":
            _test = unittest.expectedFailure(_test)
        setattr(ParityTest, f"test_{_agent}_{_control}", _test)

for _key, _fn in C.SHARED_CHECKS.items():
    _state = C.SHARED[_key][1]
    _test = _make(_fn)
    if _state == "gap":
        _test = unittest.expectedFailure(_test)
    setattr(ParityTest, f"test_shared_{_key}", _test)


if __name__ == "__main__":
    unittest.main()
