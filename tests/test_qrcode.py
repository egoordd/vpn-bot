import pytest

from services.qrcode import generate_qr_png_bytes


@pytest.mark.unit
async def test_generate_qr_png_bytes_returns_png():
    data = await generate_qr_png_bytes("wireguard config")

    assert data
    assert data.startswith(b"\x89PNG")
