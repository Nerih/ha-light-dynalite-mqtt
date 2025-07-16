from datetime import datetime
def log(msg): print(f"{datetime.now().strftime('%H:%M:%S')} 🧠 {msg}")

def float_to_q7_8(temp: float) -> tuple[int, int]:
    try:
        temp = float(temp)
        raw = int(temp * 256)
        return (raw >> 8) & 0xFF, raw & 0xFF
    except Exception as e:
        log(f"❌ float_to_q7_8 error: {e}")
        return 0, 0


def float_to_dynet_decimal(temp: float) -> tuple[int, int]:
    try:
        temp = float(temp)
        int_part = int(temp)
        decimal_part = int(round((temp - int_part) * 100))
        return int_part & 0xFF, decimal_part & 0xFF
    except Exception as e:
        log(f"❌ float_to_dynet_decimal error: {e}")
        return 0, 0


def build_area_setpoint_body(area: int, join: int, setpoint: float, device=0xBB, box=8) -> str:
    try:
        opcode = 0x56
        area_hi, area_lo = (area >> 8) & 0xFF, area & 0xFF
        box_hi, box_lo = (box >> 8) & 0xFF, box & 0xFF
        set_hi, set_lo = float_to_dynet_decimal(setpoint)

        body_bytes = [
            opcode, device,
            box_hi, box_lo,
            area_hi, area_lo,
            join,
            0x0D,
            set_hi, set_lo,
            0x00, 0x00
        ]

        return " ".join(f"{b:02X}" for b in body_bytes)

    except Exception as e:
        log(f"❌ build_area_setpoint_body error: {e}")
        return None


def build_area_temperature_body(area: int, join: int, temp: float, device=0xBB, box=8) -> str:
    try:
        opcode = 0x56
        area_hi, area_lo = (area >> 8) & 0xFF, area & 0xFF
        box_hi, box_lo = (box >> 8) & 0xFF, box & 0xFF
        temp_hi, temp_lo = float_to_dynet_decimal(temp)

        body_bytes = [
            opcode, device,
            box_hi, box_lo,
            area_hi, area_lo,
            join,
            0x0C,
            temp_hi, temp_lo,
            0x00, 0x00
        ]

        return " ".join(f"{b:02X}" for b in body_bytes)

    except Exception as e:
        log(f"❌ build_area_temperature_body error: {e}")
        return None


def build_area_preset_dynet1(area: int, preset: int, fade: int =50, channel: int = 0xFF,
                           join: int = 0xFF) -> bytes:
    """
    Build raw message body for Dynet1 Opcode 0x11: Fade Channel/Area to Preset.

    Returns:
        bytes: Raw message body (excluding start frame and checksum).
    """
    if preset>0:
        preset=preset-1
        
    try:
        body_bytes = [
            0x1C, # Byte 0
            area,         # Byte 1
            channel, # Byte 2
            0X6B, # Byte 3 opcode for Fade Channel/Area to Preset
            preset, #byte 4
            fade, # byte 5
            join,  #  join
        ]
        return " ".join(f"{b:02X}" for b in body_bytes)

    except Exception as e:
        log(f"❌ build_area_preset_dynet1 error: {e}")
        return None


def build_area_preset_body(area: int, preset: int, fade: int =50, channel: int = 0xFFFF,
                           join: int = 0xFF, device: int = 0xBB, box: int = 8) -> bytes:
    """
    Build raw message body for Dynet2 Opcode 0x11: Fade Channel/Area to Preset.

    Returns:
        bytes: Raw message body (excluding start frame and checksum).
    """
    try:
        opcode = 0x11
        area_hi, area_lo = (area >> 8) & 0xFF, area & 0xFF
        box_hi, box_lo = (box >> 8) & 0xFF, box & 0xFF
        channel_hi, channel_lo = (channel >> 8) & 0xFF, channel & 0xFF        
        preset_hi, preset_lo = (preset >> 8) & 0xFF, preset & 0xFF

        
        fade_hi = (fade >> 16) & 0xFF
        fade_mid = (fade >> 8) & 0xFF
        fade_lo = fade & 0xFF

        body_bytes = [
            opcode,         # Byte 0
            device,         # Byte 1
            box_hi, box_lo, # Byte 2–3
            area_hi, area_lo,  # Byte 4–5
            join,           # Byte 6
            0x00,     # Byte 7 – constant 0x00
            channel_hi, channel_lo,  # Byte 8–9
            preset_hi, preset_lo,    # Byte 10–11
            fade_hi, fade_mid, fade_lo,  # Byte 12–14
            0x00
            ]
        return " ".join(f"{b:02X}" for b in body_bytes)
    except Exception as e:
        log(f"❌ build_area_preset_body error: {e}")
        return None

def percent_to_dynet_level(percent: int) -> int:
    try:
        if not isinstance(percent, (int, float)):
            raise ValueError("Level must be a number")
        percent = max(0, min(int(percent), 100))
        return int(percent / 100 * 254)
    except Exception as e:
        log(f"❌ percent_to_dynet_level error: {e}")
        return 0


def build_channel_level_body(area: int, channel: int, level: int,join: int, fade: int = 50, device=0xBB, box=8 ) -> str:
    try:
        opcode = 0x10
        area_hi, area_lo = (area >> 8) & 0xFF, area & 0xFF
        box_hi, box_lo = (box >> 8) & 0xFF, box & 0xFF
        channel_hi, channel_lo = (channel >> 8) & 0xFF, channel & 0xFF

        fade_hi = (fade >> 16) & 0xFF
        fade_mid = (fade >> 8) & 0xFF
        fade_lo = fade & 0xFF

        level = percent_to_dynet_level(level)

        body_bytes = [
            opcode, device,
            box_hi, box_lo,
            area_hi, area_lo,
            join,
            0x02,
            channel_hi, channel_lo,
            level,
            0x00,
            fade_hi, fade_mid, fade_lo,
            0x00
        ]

        return " ".join(f"{b:02X}" for b in body_bytes)

    except Exception as e:
        log(f"❌ build_channel_level_body error: {e}")
        return None


def build_request_current_preset(area: int, join: int = 0xFF, channel: int = 0x00) -> bytes:
    """
    Build Dynet1 packet body for 'Request Current Preset' (Opcode 0x63).

    Parameters:
        area (int): Dynalite area (0–255)
        join (int): Join number (0–255), default 0xFF
        channel (int): Channel number (0–255), default 0

    Returns:
        bytes: 7-byte Dynet1 message body (without header/checksum)
    """
    try:
        # Only convert to 0-based if not 0xFF ("all channels")
        if channel != 0xFF:
            channel = max(0, channel - 1)
        body_bytes = [
            0X1C,
            area & 0xFF, # Byte 1: area
            0x00,        # Byte 2: unused
            0x63,        # Byte 3: opcode
            channel  & 0xFF,  # Byte 4: channel (zero-based)
            0x00,        # Byte 5: unused
            join & 0xFF  # Byte 6: join
        ]
        return " ".join(f"{b:02X}" for b in body_bytes)

    except Exception as e:
        log(f"❌ build_channel_level_body error: {e}")
        return None
