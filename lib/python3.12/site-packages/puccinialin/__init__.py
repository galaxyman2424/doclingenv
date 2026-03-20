from __future__ import annotations

from ._setup_rust import setup_rust
from ._target import get_triple

__all__ = ["setup_rust", "get_triple"]
