"""List every strategy, its stage, broker, and halt status."""
from __future__ import annotations

from core.live import state as state_store
from runners._common import discover


def main() -> None:
    manifests = discover()
    if not manifests:
        print("No strategies found under strategies/.")
        return
    print(f"{'strategy':<18}{'stage':<12}{'broker':<8}{'halted':<8}notes")
    for name in sorted(manifests):
        m = manifests[name]
        st = state_store.load(name)
        print(f"{name:<18}{m.stage.name:<12}{m.broker:<8}"
              f"{('YES' if st.halted else '-'):<8}{m.notes}")


if __name__ == "__main__":
    main()
