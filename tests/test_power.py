from doggy.power import PowerMonitor


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_parses_undervolt_now_and_since_boot():
    s = PowerMonitor(reader=lambda: 0x1_0001).read()
    assert s is not None and s.undervolt_now and s.undervolt_since_boot


def test_ok_when_no_bits_set():
    s = PowerMonitor(reader=lambda: 0x0).read()
    assert s is not None and not s.undervolt_now and not s.undervolt_since_boot


def test_thermal_only_mask_is_not_read_as_power():
    # 0xe0000 = historical thermal bits (17/18/19); no under-voltage bit set.
    s = PowerMonitor(reader=lambda: 0xE0000).read()
    assert s is not None and not s.undervolt_now and not s.undervolt_since_boot


def test_undervolt_since_boot_without_now():
    # bit 16 set, bit 0 clear -> dipped earlier, fine now.
    s = PowerMonitor(reader=lambda: 0x1_0000).read()
    assert s is not None and not s.undervolt_now and s.undervolt_since_boot


def test_unavailable_reader_returns_none():
    assert PowerMonitor(reader=lambda: None).read() is None


def test_caches_within_min_interval_then_rereads():
    calls: list[int] = []

    def reader() -> int:
        calls.append(1)
        return 0x1

    clk = FakeClock()
    m = PowerMonitor(clock=clk, min_interval=15.0, reader=reader)
    m.read()
    m.read()
    assert len(calls) == 1  # second call served from cache
    clk.t = 20.0
    m.read()
    assert len(calls) == 2  # re-read after the interval elapses
