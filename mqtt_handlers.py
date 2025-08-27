# mqtt_handlers.py
import json
import uuid
import asyncio
from datetime import datetime, timezone

from config import (
    MQTT_HOST, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD,
    MQTT_DYNALITE_PREFIX, MQTT_BRIDGE_WILL, MQTT_DEBUG,
    MQTT_DYNALITE_WILL, MQTT_HOMEASSISTANT_PREFIX
)
from mqtt.publisher import MQTTPublisher
from utils import log

mqtt_client = None
bridge_online = {"dynalite": False}

def pub2dynet(type, hex_string,pending_responses, comment=""):
    response_id = uuid.uuid4().hex
    payload = {
        "type": type,
        "hex_string": hex_string,
        "response_id": response_id
    }
    mqtt_client.publish(f"{MQTT_DYNALITE_PREFIX}/set", json.dumps(payload))
    pending_responses[response_id] = {
        "comment": comment,
        "sent_at": datetime.now(timezone.utc)
    }

def handle_mqtt_connect(client, userdata, flags, rc):
    if rc != 0:
        log(f"❌ Connection failed with code {rc}")
        return

    try:
        client.subscribe(MQTT_DYNALITE_WILL)
        log(f"📡 Subscribed to {MQTT_DYNALITE_WILL}")

        client.subscribe(f"{MQTT_DYNALITE_PREFIX}/set/res/#")
        log(f"📡 Subscribed to {MQTT_DYNALITE_PREFIX}/set/res/#")

        client.subscribe(MQTT_DYNALITE_PREFIX)
        log(f"📡 Subscribed to {MQTT_DYNALITE_PREFIX}")

        client.subscribe(f"{MQTT_HOMEASSISTANT_PREFIX}/light/+/+/brightness/set")
        log(f"📡 Subscribed to {MQTT_HOMEASSISTANT_PREFIX}/light/+/+/brightness/set")
        #for covers
        client.subscribe(f"{MQTT_HOMEASSISTANT_PREFIX}/cover/+/+/set")
        log(f"📡 Subscribed to {MQTT_HOMEASSISTANT_PREFIX}/cover/+/+/set")
    except Exception as e:
        log(f"❌ Failed to subscribe: {e}")

def sweep_pending_responses(pending_responses,ttl=15):
    async def sweeper():
        while True:
            now = datetime.now(timezone.utc)
            expired = [rid for rid, meta in pending_responses.items()
                       if (now - meta["sent_at"]).total_seconds() > ttl]
            for rid in expired:
                meta = pending_responses.pop(rid, None)
                log(f"⚠️❌⚠️ Expired Response ID {rid} — Full data: {json.dumps(meta, default=str)}")
            await asyncio.sleep(ttl)
    return sweeper()

def start_mqtt(dynalite_map, on_message=None):
    global mqtt_client
    mqtt_client = MQTTPublisher(
        mqtt_username=MQTT_USERNAME,
        mqtt_password=MQTT_PASSWORD,
        mqtt_host=MQTT_HOST,
        mqtt_port=MQTT_PORT,
        will_topic=f"{MQTT_BRIDGE_WILL}/status",
        mqtt_debug=MQTT_DEBUG
    )
    mqtt_client.on_connect = handle_mqtt_connect
    if on_message:
        mqtt_client.on_message = on_message
    return mqtt_client
