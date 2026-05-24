from __future__ import annotations

import asyncio
from io import BytesIO

import qrcode


def _generate_qr_png_bytes(config_text: str) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(config_text)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def generate_qr_png_bytes(config_text: str) -> bytes:
    return await asyncio.to_thread(_generate_qr_png_bytes, config_text)
