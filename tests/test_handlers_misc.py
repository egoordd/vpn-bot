from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

@pytest.mark.unit
async def test_help_command_shows_connect_and_support():
    from bot.handlers import help as help_handler