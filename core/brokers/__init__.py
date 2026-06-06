"""core.brokers — pluggable broker adapters.

A strategy never imports a broker; its manifest names one ("fyers") and the
runner injects the adapter. Adding a market (e.g. forex) = one new package
under core/brokers/ implementing DataAdapter, registered here.
"""
from __future__ import annotations

from core.brokers.base import DataAdapter

_REGISTRY: dict[str, str] = {
    # name -> "module:Class", resolved lazily so importing core.brokers
    # doesn't drag in every broker SDK.
    "fyers": "core.brokers.fyers:FyersDataAdapter",
}


def get_data_adapter(name: str, **kwargs) -> DataAdapter:
    try:
        target = _REGISTRY[name]
    except KeyError:
        raise ValueError(f"Unknown broker {name!r}; known: {sorted(_REGISTRY)}") from None
    module_name, _, attr = target.partition(":")
    import importlib
    cls = getattr(importlib.import_module(module_name), attr)
    return cls(**kwargs)
