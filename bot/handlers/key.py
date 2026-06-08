from bot.handlers.connect_device import (  # noqa: F401
    connect_app_handler,
    connect_device_handler,
    generate_qr_png_bytes,
    rotate_user_key,
    router,
)

get_key_handler = connect_device_handler
