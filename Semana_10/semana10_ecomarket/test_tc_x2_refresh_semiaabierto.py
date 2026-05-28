import pytest

from test_circuit_breaker import test_tc_x2 as _test_tc_x2


@pytest.mark.asyncio
async def test_tc_x2_refresh_semiaabierto():
    await _test_tc_x2()
