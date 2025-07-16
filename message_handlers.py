# message_handlers.py
import json
import re
from utils import get_val_by_mestype, log
from mqtt_handlers import pub2dynet
from datetime import datetime, timezone
from collections import defaultdict

from helpers.dynet_mqtt import (
    build_area_preset_body,
    build_request_current_preset,
    build_area_preset_dynet1
)
from config import (
    MQTT_HOMEASSISTANT_PREFIX,
    PRESET_NONE_OFF
)


def handle_ha_brightness_command(topic: str, payload: str, dynalite_map: dict,mqtt_client,pending_responses):
    match = re.search(r"dynet_area_(\d+)/channel_(\d+|all)/", topic)
    if not match:
        log(f"❌ Invalid HA brightness topic: {topic}")
        return

    area = int(match.group(1))
    str_channel = match.group(2)
    brightness = int(payload)

    log(f"HA Brightness Set → Area: {area}, Channel: {str_channel}, Brightness: {brightness}")

    presets, levels = [
        dynalite_map.get("areas", {}).get(area, {}).get("channels", {}).get(str_channel, {}).get(k,
            dynalite_map.get("defaults", {}).get(k, [])) for k in ("presets", "levels")
    ]

    if not levels or not presets:
        log(f"⚠️ No presets/levels for area {area}, channel {str_channel}")
        return

    closest_level = min(levels, key=lambda lv: abs(lv - brightness))
    idx = levels.index(closest_level)
    preset = presets[idx] if idx < len(presets) else None

    if str_channel == "all":
        zero_based_channel = 0x0000
        channel = 0xFF
    else:
        zero_based_channel = int(str_channel)
        channel = int(str_channel)

    #TODO check if map says to send as DYNET1 or 2 (some macro/task listeners only support DYNET1)
    #   specifically "floor all" controls
    dynet_version = dynalite_map.get("areas", {}).get(area, {}).get("dynet", "dynet2")

    if dynet_version == "dynet2":
        hex_msg = build_area_preset_body(area=area, preset=preset, channel=zero_based_channel)
    else:
        hex_msg = build_area_preset_dynet1(area=area, preset=preset, channel=channel)
    
    log(f"📤 Sending Dynalite Packet → {hex_msg}")
    pub2dynet(type=dynet_version, hex_string=hex_msg, pending_responses=pending_responses)

    # Request confirmation, default ack is False, dynet version is always 1
    should_ack = dynalite_map.get("areas", {}).get(area, {}).get("ack", False)
    if should_ack:
        confirm = build_request_current_preset(area=area, channel=channel)
        pub2dynet(type="dynet1", hex_string=confirm, pending_responses=pending_responses)
        log(f"✅ Confirmation requested for area {area} channel {channel}")
    else:
        log(f"ℹ️ ACK=False for area {area}, no confirmation requested")
        
    # Update MQTT state (ahead of confirmation)

    if channel is None:
        log(f"⚠️ Channel is None, so setting Channel to 'all'")
        channel = "all"

    if channel == 0xFF or channel == 0xFFFF:
        channel = "all"
    elif isinstance(channel, int) and type == "dynet1":
        channel += 1

    area_cfg = dynalite_map.get("areas", {}).get(area)
    if not area_cfg:
        log(f"⚠️ Area {area} not found in config — skipping")
        return

    if not str(channel) in area_cfg.get("channels", {}):
        log(f"⛔ Channel {channel} not mapped in area {area}")
        return

    presets, levels = [
        dynalite_map["areas"][area]["channels"].get(str(channel), {}).get(k, dynalite_map.get("defaults", {}).get(k, []))
        for k in ("presets", "levels")
    ]

    #send the MQTT command here to update the levels
    if preset in presets:
        idx = presets.index(preset)
        level = levels[idx] if idx < len(levels) else 0
        topic_out = f"{MQTT_HOMEASSISTANT_PREFIX}/light/dynet_area_{area}/channel_{channel}/brightness"
        mqtt_client.publish(topic_out, level)
        #publish_if_changed(mqtt_client=mqtt_client,topic=topic_out,brightness=level)
        log(f"✅ Preset {preset} = Brightness: {round((level/255)*100,0)}% published to {topic_out}")

        if str(channel) == "all":
            # Master level already determined above
            for ch_str, ch_cfg in area_cfg.get("channels", {}).items():
                if ch_str == "all":
                    continue  # Skip master itself
                ch_presets = ch_cfg.get("presets", dynalite_map.get("defaults", {}).get("presets", []))
                ch_levels = ch_cfg.get("levels", dynalite_map.get("defaults", {}).get("levels", []))
                if ch_levels:
                    # Find the closest matching level in this channel
                    closest_level = min(ch_levels, key=lambda lv: abs(lv - level))
                    level_idx = ch_levels.index(closest_level)
                else:
                    closest_level = 0
                    level_idx = 0
                # Optional: also map back to a preset if needed
                ch_preset = ch_presets[level_idx] if level_idx < len(ch_presets) else None
                topic_out = f"{MQTT_HOMEASSISTANT_PREFIX}/light/dynet_area_{area}/channel_{ch_str}/brightness"
                #do not use cache
                #publish_if_changed(mqtt_client=mqtt_client,topic=topic_out,brightness=level)                        
                mqtt_client.publish(topic_out, closest_level)
                log(f"✅ Master preset {preset} → Channel {ch_str} brightness {round((closest_level/255)*100,0)}% published to {topic_out}")
                
        return

    else:
        log(f"⛔ Preset: {preset} not found in {presets}")    

def handle_dynet_packet(parsed, dynalite_map,mqtt_client):
    try:
        description = str(parsed.get("description", "").lower())
        type = parsed.get("type")
        fields = parsed.get("fields")
        field_types = parsed.get("field_types")

        if any(phrase in description for phrase in [
            "select preset", "recall preset", "area to preset",
            "reply current preset", "reply channel current preset"
        ]):

            
            area = get_val_by_mestype("MES_AREA", fields, field_types, True)
            preset = get_val_by_mestype("MES_PRESET" if type == "dynet1" else "MES_PRESET_DYNET2", fields, field_types, True)
            channel = get_val_by_mestype("MES_CHANNEL_ZERO_BASED" if type == "dynet1" else "MES_CHANNEL_DYNET2_LOGICAL", fields, field_types, True)

            if area is None or preset is None:
                log(f"⛔ Incomplete Dynet message: {parsed}")
                return

            if channel is None:
                log(f"⚠️ Channel is None, so setting Channel to 'all'. Description: '{description}'")
                channel = "all"

            if channel == 0xFF or channel == 0xFFFF:
                channel = "all"
            elif isinstance(channel, int) and type == "dynet1":
                channel += 1

            area_cfg = dynalite_map.get("areas", {}).get(area)
            if not area_cfg:
                log(f"⚠️ Area {area} not found in config — skipping")
                return

            if not str(channel) in area_cfg.get("channels", {}):
                log(f"⛔ Channel {channel} not mapped in area {area}")
                return

            presets, levels = [
                dynalite_map["areas"][area]["channels"].get(str(channel), {}).get(k, dynalite_map.get("defaults", {}).get(k, []))
                for k in ("presets", "levels")
            ]

            if preset in presets:
                idx = presets.index(preset)
                level = levels[idx] if idx < len(levels) else 0
                topic_out = f"{MQTT_HOMEASSISTANT_PREFIX}/light/dynet_area_{area}/channel_{channel}/brightness"
                mqtt_client.publish(topic_out, level)
                #publish_if_changed(mqtt_client=mqtt_client,topic=topic_out,brightness=level)
                log(f"✅ Preset {preset} = Brightness: {round((level/255)*100,0)}% published to {topic_out}")

                if str(channel) == "all":
                    # Master level already determined above
                    for ch_str, ch_cfg in area_cfg.get("channels", {}).items():
                        if ch_str == "all":
                            continue  # Skip master itself
                        ch_presets = ch_cfg.get("presets", dynalite_map.get("defaults", {}).get("presets", []))
                        ch_levels = ch_cfg.get("levels", dynalite_map.get("defaults", {}).get("levels", []))
                        if ch_levels:
                            # Find the closest matching level in this channel
                            closest_level = min(ch_levels, key=lambda lv: abs(lv - level))
                            level_idx = ch_levels.index(closest_level)
                        else:
                            closest_level = 0
                            level_idx = 0
                        # Optional: also map back to a preset if needed
                        ch_preset = ch_presets[level_idx] if level_idx < len(ch_presets) else None
                        topic_out = f"{MQTT_HOMEASSISTANT_PREFIX}/light/dynet_area_{area}/channel_{ch_str}/brightness"
                        #do not use cache
                        #publish_if_changed(mqtt_client=mqtt_client,topic=topic_out,brightness=level)                        
                        mqtt_client.publish(topic_out, closest_level)
                        log(f"✅ Master preset {preset} → Channel {ch_str} brightness {round((closest_level/255)*100,0)}% published to {topic_out}")
                        
                return

            else:
                log(f"⛔ Preset: {preset} not found in {presets}")

    except Exception as e:
        log(f"❌ Failed to handle Dynet packet: {e}")


def handle_response_ack(topic, payload, pending_responses, mqtt_client):
    try:
        response_id = topic.split("/")[-1]
        result = json.loads(payload)
        entry = pending_responses.pop(response_id, None)
        if entry:
            elapsed = (datetime.now(timezone.utc) - entry["sent_at"]).total_seconds()
            comment = entry.get("comment", "-")
            status = result.get("status", "Unknown")
            if status.lower() != "ok":
                log(f"❌❌❌ Response ID {response_id} failed — Status: {status}, Time: {elapsed:.2f}s, Comment: {comment}")
            else:
                #log(f"✅ Confirmed sent Dynet")
                return
    except Exception as e:
        log(f"❌ Error handling response ack: {e}")


def is_preset_related(description: str) -> bool:
    desc = description.lower()
    return any(k in desc for k in [
        "select preset",
        "recall preset",
        "area to preset",
        "reply current preset",
        "reply channel current preset",
        "reply with current preset"
    ])
