from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import openziti


@dataclass(frozen=True)
class Identity:
    path: Path


def load_context(identity_path: str) -> openziti.ZitiContext:
    ctx, err = openziti.load(identity_path)
    if err != 0:
        raise RuntimeError(
            f"Failed to load Ziti identity from {identity_path!r} (err={err}). "
            "Ensure the identity JSON exists and is readable."
        )
    return ctx
