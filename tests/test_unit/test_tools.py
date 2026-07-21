import asyncio
from tools.calculator import calculate
from tools.datetime_tool import get_datetime
from tools.system_info import get_system_info
from tools.clipboard_tool import clipboard_action
from tools.pause_tool import pause_listening
from tools.volume_control import control_volume

def test_calculator_tool():
    res = calculate("15 percent of 200")
    assert "30" in res

def test_datetime_tool():
    res = get_datetime("")
    assert len(res) > 5
    assert "20" in res # year

async def test_system_info_tool():
    res = await get_system_info("battery")
    assert isinstance(res, str)
    assert len(res) > 0

async def test_clipboard_action():
    # Just ensure it doesn't crash on read
    res = await clipboard_action("read")
    assert isinstance(res, str)

def test_pause_listening():
    res = pause_listening("")
    assert res == "__PAUSE_MODE_TRIGGER__"

async def test_volume_control():
    # Only test mute/unmute to avoid disturbing audio levels too much
    res = await control_volume("mute")
    assert "Muted" in res or "muted" in res.lower()
