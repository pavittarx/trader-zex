"""Network-free smoke test for the momentum harness.

Proves the instrument still has statistical power (recovers a planted momentum
signal) and does not manufacture signal (stays ~flat on pure noise). Mirrors
`momentum_ic.py --self-test` as pytest assertions. No market data needed.
"""
from strategies.momentum.research import momentum_ic as m


def _ic_t(momentum: bool, seed: int):
    rec = m.build_records(m._synth_panel(momentum=momentum, seed=seed))
    ic, t, _ = m.pooled_ic(rec)
    return ic, t


def test_recovers_planted_momentum():
    ic, t = _ic_t(momentum=True, seed=1)
    assert ic > 0 and t > 2, f"expected IC>0, t>2 on planted signal; got IC={ic:.3f}, t={t:.2f}"


def test_no_signal_on_noise():
    ic, t = _ic_t(momentum=False, seed=2)
    assert abs(t) < 2, f"expected |t|<2 on pure noise; got IC={ic:.3f}, t={t:.2f}"
