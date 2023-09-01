import json
from datetime import timedelta
from threading import Lock
from types import SimpleNamespace

import paho.mqtt.client as mqtt
import requests
from cachetools import cached, TTLCache, LRUCache
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

from config import MQTT
from config import USER_AGENT

geocoder_url = "https://geocode.maps.co/search"
weather_url = "https://api.met.no/weatherapi/locationforecast/2.0/complete.json"

# Global shared instance for converting lat/lon to a timezone
timezone_finder = TimezoneFinder()

# Similar for geocoding
geolocator = Nominatim(user_agent=USER_AGENT)

# Cache for place -> location lookups
geocode_cache = {}

# Cache for reverse geocaching
rev_geocode_cache = LRUCache(1000)


@cached(cache=TTLCache(100, ttl=timedelta(minutes=10).seconds), lock=Lock())
def get_forecast_(lat: float, lon: float):
    try:
        parameters = {
            "lat": {lat},
            "lon": {lon}
        }
        headers = {
            "User-Agent": USER_AGENT
        }

        return requests.get(weather_url, params=parameters, headers=headers).json()
    except Exception as ex:
        print(f"Failed to get forecast: {ex}")
        return None


def geocode_place(place: str):
    cache_key = place.lower()
    if cache_key not in geocode_cache:
        location = geolocator.geocode(place)
        geocode_cache[cache_key] = location
        print(f"Geocode miss for '{place}': {location}")
    return geocode_cache[cache_key]


def rev_geocode(lat: float, lon: float):
    cache_key = f"{lat:.3f},{lon:.3f}"
    if cache_key not in rev_geocode_cache:
        location = geolocator.reverse(f"{lat}, {lon}")
        rev_geocode_cache[cache_key] = location
        print(f"Reverse geocode miss for {lat}, {lon}: {location}")

        if "address" in location.raw:
            address = location.raw["address"]
            if "suburb" in address:
                suburb = address["suburb"]
            city = address["city"]
            state = location.raw["address"]["state"]
            location.raw["display_name"] = ", ".join([suburb, city, state])
    return rev_geocode_cache[cache_key]


def get_forecast(lat: float, lon: float):
    # For some reason PyCharm thinks that calling a method with a `@cached` decorator (when it has more than one
    # parameter?) is "calling" it? Until this is fixed, suppress the warning here.
    # Issue: https://youtrack.jetbrains.com/issue/PY-52210
    # noinspection PyCallingNonCallable
    return get_forecast_(lat, lon)


def place_request(place: str) -> dict:
    location = geocode_place(place)
    lat = float(location.latitude)
    lon = float(location.longitude)
    timezone = timezone_finder.timezone_at(lat=lat, lng=lon)
    forecast = get_forecast(lat, lon)
    return {
        "location": location.raw,
        "timezone": timezone,
        "forecast": forecast,
    }


def point_request(lat: float, lon: float) -> dict:
    location = rev_geocode(lat, lon)
    timezone = timezone_finder.timezone_at(lat=lat, lng=lon)
    forecast = get_forecast(lat, lon)
    return {
        "location": location.raw,
        "timezone": timezone,
        "forecast": forecast,
    }


def on_connect(client, userdata, flags, rc):
    # This will be called once the client connects
    print(f"Connected with result code {rc}")
    # MQTT isn't really an RPC framework, so we use two topics
    topic = MQTT["topic"]
    client.subscribe(f"{topic}/request")

    topic = MQTT["topic"]
    client.publish(f"{topic}/debug", payload="MQTT Weather Started")


def on_message(client, userdata, msg):
    topic = MQTT["topic"]
    print(f"MQTT request received [{msg.topic}]: {msg.payload}")
    try:
        req = json.loads(msg.payload, object_hook=lambda d: SimpleNamespace(**d))
    except json.JSONDecodeError as ex:
        print(f"Error decoding request: {ex}")
        error = {
            "payload": f"Error parsing payload: {msg.payload}"
        }
        client.publish(f"{topic}/response", payload=json.dumps(error))
        return

    if hasattr(req, "place"):
        print(f"Place lookup: {req.place}")
        response = place_request(req.place)
    elif hasattr(req, "lat") and hasattr(req, "lon"):
        print(f"Lat/lon lookup: {req.lat}, {req.lon}")
        response = point_request(req.lat, req.lon)
    else:
        print(f"Unknown request: {req}")
        response = {
            "type": "error"
        }
    client.publish(f"{topic}/response", payload=json.dumps(response))


def main():
    client = mqtt.Client(MQTT["client_id"])
    client.on_connect = on_connect
    client.on_message = on_message
    client.username_pw_set(MQTT["user"], MQTT["password"])
    client.connect(MQTT["broker"], MQTT["port"])
    client.loop_forever()  # Start networking daemon


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    main()
