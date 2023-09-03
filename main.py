import argparse
import json
from datetime import timedelta
from threading import Lock
from types import SimpleNamespace

import paho.mqtt.client as mqtt
import requests
import tomli
from cachetools import cached, TTLCache, LRUCache
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

from dotdict import DotDict

geocoder_url = "https://geocode.maps.co/search"
weather_url = "https://api.met.no/weatherapi/locationforecast/2.0/complete.json"

global_config = DotDict()

# Global shared instance for converting lat/lon to a timezone
timezone_finder = TimezoneFinder()

# Similar for geocoding
geolocator: Nominatim = None

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
            "User-Agent": global_config.api.user_agent
        }

        return requests.get(weather_url, params=parameters, headers=headers).json()
    except Exception as ex:
        print(f"Failed to get forecast: {ex}")
        return None


def geocode_place(place: str):
    cache_key = place.lower()
    if cache_key not in geocode_cache:
        location = geolocator.geocode(place)
        geocode_cache[cache_key] = DotDict(location.raw)
        print(f"Geocode miss for '{place}': {location}")
    return geocode_cache[cache_key]


def rev_geocode(lat: float, lon: float):
    cache_key = f"{lat:.3f},{lon:.3f}"
    if cache_key not in rev_geocode_cache:
        location = geolocator.reverse(f"{lat}, {lon}")

        # Because we're passing all of this back as JSON,
        # just take the "raw" dict version and use that
        location = DotDict(location.raw)

        # If there's an `address`, the `display_name`
        # will end up being something like,
        # "123 Princes Street, Edinburgh EH2 4AD United Kingdom"
        # which is just way too detailed for what is needed.
        if "address" in location:
            address = location.address
            if "suburb" in address:
                suburb = address.suburb
            else:
                suburb = None
            city = address.city
            state = address.state
            location.display_name = ", ".join([suburb, city, state])

        rev_geocode_cache[cache_key] = location
        print(f"Reverse geocode miss for {lat}, {lon}: {location}")
    return rev_geocode_cache[cache_key]


def get_forecast(lat: float, lon: float):
    # For some reason PyCharm thinks that calling a method with a `@cached` decorator (when it has more than one
    # parameter?) is "calling" it? Until this is fixed, suppress the warning here.
    # Issue: https://youtrack.jetbrains.com/issue/PY-52210
    # noinspection PyCallingNonCallable
    return get_forecast_(lat, lon)


def place_request(place: str) -> dict:
    try:
        location = geocode_place(place)
    except Exception as e:
        return {
            "topic": "error",
            "error": "GEOCODE_ERROR",
            "msg": f"Failed to geocode {place}: {e}"
        }

    lat = float(location.lat)
    lon = float(location.lon)
    timezone = timezone_finder.timezone_at(lat=lat, lng=lon)
    forecast = get_forecast(lat, lon)
    return {
        "topic": "place_request",
        "location": location,
        "timezone": timezone,
        "forecast": forecast,
    }


def point_request(lat: float, lon: float) -> dict:
    try:
        location = rev_geocode(lat, lon)
    except Exception as e:
        return {
            "topic": "error",
            "error": "GEOCODE_ERROR",
            "msg": f"Failed to reverse-geocode {lat}, {lon}: {e}"
        }

    timezone = timezone_finder.timezone_at(lat=lat, lng=lon)
    forecast = get_forecast(lat, lon)
    return {
        "topic": "point_request",
        "location": location,
        "timezone": timezone,
        "forecast": forecast,
    }


def on_connect(client, userdata, flags, rc):
    # This will be called once the client connects
    print(f"Connected with result code {rc}")
    # MQTT isn't really an RPC framework, so we use two topics
    topic = global_config.mqtt.topic
    client.subscribe(f"{topic}/request")

    topic = global_config.mqtt.topic
    client.publish(f"{topic}/debug", payload="MQTT Weather Started")


def on_message(client, userdata, msg):
    topic = global_config.mqtt.topic
    print(f"MQTT request received [{msg.topic}]: {msg.payload}")
    try:
        req = json.loads(msg.payload, object_hook=lambda d: SimpleNamespace(**d))
    except json.JSONDecodeError as ex:
        print(f"Error decoding request: {ex}")
        error = {
            "topic": "error",
            "msg": f"Error parsing payload: {msg.payload}"
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
            "topic": "error",
            "msg": f"Unknown request: {req}"
        }
    client.publish(f"{topic}/response", payload=json.dumps(response))


def add_locations_to_cache(locations: list[DotDict]):
    for location in locations:
        location = DotDict(location)
        if "name" in location:
            geocode_cache[location.name.lower()] = location
        elif "names" in location:
            for name in location.names:
                geocode_cache[name.lower()] = location
        else:
            print(f"Skipped malformed location: {location}")


def main():
    global global_config
    global geolocator

    parser = argparse.ArgumentParser(description="MQTT Weather API")
    parser.add_argument("--config", dest="config_path", required=True,
                        help="path to file containing custom locations")
    args = parser.parse_args()

    with open(args.config_path, "rb") as config_file:
        toml_dict = tomli.load(config_file)
    global_config = DotDict(toml_dict)

    add_locations_to_cache(global_config.locations)

    # Global geolocation object
    geolocator = Nominatim(user_agent=global_config.api.user_agent)

    # Setup and connect to MQTT
    client = mqtt.Client(global_config.mqtt.client_id)
    client.on_connect = on_connect
    client.on_message = on_message
    client.username_pw_set(global_config.mqtt.user, global_config.mqtt.password)
    client.connect(global_config.mqtt.broker, global_config.mqtt.port)
    client.loop_forever()  # Start networking daemon


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    main()
