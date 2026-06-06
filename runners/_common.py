"""Shared runner machinery: discovery, stage gates, broker injection."""
from __future__ import annotations

import importlib
import pkgutil
import sys

from core.brokers import get_data_adapter
from core.manifest import Manifest, Stage


def discover() -> dict[str, Manifest]:
    """All strategies under strategies/ that export a MANIFEST."""
    import strategies
    out: dict[str, Manifest] = {}
    for info in pkgutil.iter_modules(strategies.__path__):
        if info.name.startswith("_"):
            continue  # _template
        try:
            mod = importlib.import_module(f"strategies.{info.name}.manifest")
        except ModuleNotFoundError:
            continue
        manifest = getattr(mod, "MANIFEST", None)
        if manifest is not None:
            out[manifest.name] = manifest
    return out


def load_manifest(name: str) -> Manifest:
    try:
        mod = importlib.import_module(f"strategies.{name}.manifest")
        return mod.MANIFEST
    except ModuleNotFoundError:
        known = sorted(discover())
        sys.exit(f"Unknown strategy {name!r}. Known: {known}")


def require_stage(manifest: Manifest, minimum: Stage, *, exact: bool = False) -> None:
    """Stage gate. Exits non-zero if the strategy hasn't earned this environment."""
    if manifest.stage == Stage.dropped:
        sys.exit(f"{manifest.name} is DROPPED — see strategies/{manifest.name}/STATUS.md")
    ok = manifest.stage == minimum if exact else manifest.stage >= minimum
    if not ok:
        op = "==" if exact else ">="
        sys.exit(f"{manifest.name} is stage={manifest.stage.name}; "
                 f"this runner needs stage {op} {minimum.name}. "
                 f"Promote it in strategies/{manifest.name}/manifest.py "
                 f"(and record why in STATUS.md) first.")


def require_not_halted(manifest: Manifest) -> None:
    """Refuse to run a strategy whose kill-switch has tripped."""
    from core.live import state as state_store
    st = state_store.load(manifest.name)
    if st.halted:
        sys.exit(f"{manifest.name} is HALTED ({st.halted_reason} @ {st.halted_at}). "
                 f"Reset with: python -m core.live.monitor {manifest.name} --reset-halt")


def broker_for(manifest: Manifest):
    """Instantiate the data adapter the manifest names. Strategies never do this."""
    return get_data_adapter(manifest.broker)
