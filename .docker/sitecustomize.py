"""Docker helper to ensure the generated config module is importable.

Problem:
- The project uses create_app('config') which imports module name 'config'.
- In development, the repo is often bind-mounted to /app.
- Python always puts the current working directory ("" -> /app) at the front of sys.path.
- If a /app/config.py exists (from the repo), it will shadow the generated config.

Solution:
Put /app/state at the *front* of sys.path so /app/state/config.py wins.
"""

from __future__ import annotations

import os
import sys


def _prioritize_state_dir() -> None:
    state_dir = os.getenv("STATE_DIR", "/app/state")
    # Move /app/state to the front of sys.path (even before the CWD entry).
    try:
        while state_dir in sys.path:
            sys.path.remove(state_dir)
    except ValueError:
        pass
    sys.path.insert(0, state_dir)


_prioritize_state_dir()

