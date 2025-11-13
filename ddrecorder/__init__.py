"""
DDRecorderV2 runtime package.

This module exposes the `run` helper so callers can embed the recorder in
their own tooling if desired:

```python
from ddrecorder import run

run("config/config.json")
```
"""

from .cli import run

__all__ = ["run"]
