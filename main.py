# app.py - requirements.txt 
import asyncio
import json
from config_loader import load_dynalite_config
from mqtt_handlers import start_mqtt, sweep_pending_responses
from utils import log
from webui import init_web_ui, run_web_ui

from discovery import publish_discovery
from message_handlers import (
    handle_ha_brightness_command,
    handle_ha_cover_command,
    handle_dynet_packet,
    handle_response_ack
)

from config import (
     MQTT_DYNALITE_PREFIX, MQTT_DYNALITE_WILL, CONFIG_PORT, CONFIG_PATH,MQTT_BRIDGE_WILL
)


bridge_online = {"dynalite": False} # Track bridge status
dynalite_map = {}  # Global map, shared across modules
mqtt_client = None  # Global MQTT client
pending_responses = {} #Response tracker

def reload_dynalite_config():
    global dynalite_map
    dynalite_map = load_dynalite_config(CONFIG_PATH)
    log("🔄 Dynalite config reloaded.")
    #renamed publish discovery, to reflect this code now handles ha-covers too
    publish_discovery(mqtt_client, dynalite_map)
    log("🔄 Dynalite config reloaded.")


def mqtt_callback(topic, payload):
    global pending_responses
    payload_lower = payload.strip().lower()

    if topic == MQTT_DYNALITE_WILL:
        if payload_lower == "online":
            bridge_online["dynalite"] = True
            log("🔌 Dynalite bridge is ONLINE.")
            mqtt_client.publish(MQTT_BRIDGE_WILL, "online", retain=True)
        elif payload_lower == "offline":
            bridge_online["dynalite"] = False
            log("❌ Dynalite bridge is OFFLINE.")
            mqtt_client.publish(MQTT_BRIDGE_WILL, "offline", retain=True)
        else:
            log(f"⚠️ Unrecognized payload on Dynalite will topic: '{payload}'")
        return  # always handle will updates

    # Block all further processing if Dynalite is offline
    if not bridge_online["dynalite"]:
        log(f"⛔ Ignoring MQTT message on {topic} because Dynalite bridge is offline.")
        return
    
    # Process normal messages only if Dynalite is online
    if topic.startswith("homeassistant/light/dynet_area_") and topic.endswith("/brightness/set"):
        handle_ha_brightness_command(topic, payload, dynalite_map, mqtt_client, pending_responses)

    if topic.startswith("homeassistant/cover/dynet_area_") and topic.endswith("/set"):
        handle_ha_cover_command(topic, payload, dynalite_map, mqtt_client, pending_responses)
        
    elif topic == MQTT_DYNALITE_PREFIX:
        try:
            parsed = json.loads(payload)
            handle_dynet_packet(parsed, dynalite_map, mqtt_client)
        except Exception as e:
            log(f"❌ Invalid Dynalite JSON: {e}")
    elif topic.startswith(f"{MQTT_DYNALITE_PREFIX}/set/res/"):
        handle_response_ack(topic, payload, pending_responses, mqtt_client)


async def main():    
    global mqtt_client
    global dynalite_map
    global pending_responses
    log("🚀 Starting HA Climate → Dynalite Bridge")

    #temp
    #dynalite_map = load_dynalite_config(CONFIG_PATH)
    #publish_discovery(mqtt_client, dynalite_map)
    

    init_web_ui(CONFIG_PATH, reload_dynalite_config)
    run_web_ui()
    log(f"🌐 Web UI available at http://localhost:{CONFIG_PORT}")
    
    dynalite_map = load_dynalite_config(CONFIG_PATH)
    mqtt_client = start_mqtt(dynalite_map, on_message=mqtt_callback)

    publish_discovery(mqtt_client, dynalite_map)
    
    asyncio.create_task(sweep_pending_responses(pending_responses))

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        log("🛑 Shutting down...")


if __name__ == "__main__":
    asyncio.run(main())
