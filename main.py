import argparse
import pprint
from datetime import timedelta
from threading import Lock

import requests
import tomli
from cachetools import cached, TTLCache, LRUCache
from flask import Flask, jsonify, Response
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

from dotdict import DotDict

# MET Norway (for worldwide forecasts)
met_no_api = "https://api.met.no/weatherapi/locationforecast/2.0/complete.json"
# UK Met Office (for forecasts inside the UK)
met_uk_api = "https://data.hub.api.metoffice.gov.uk/sitespecific/v0/point/hourly"

global_config = DotDict()

# Global shared instance for converting lat/lon to a timezone
timezone_finder = TimezoneFinder()

# Similar for geocoding
geolocator: Nominatim | None = None

# Cache for place -> location lookups
geocode_cache = {}

# Cache for reverse geocaching
rev_geocode_cache = LRUCache(1000)

# Set up Flask app
app = Flask(__name__)


# Gets a forecast from the Norwegian MET service
@cached(cache=TTLCache(100, ttl=timedelta(minutes=10).seconds), lock=Lock())
def get_forecast_no(lat: float, lon: float):
    try:
        parameters = {
            "lat": {lat},
            "lon": {lon}
        }
        headers = {
            "User-Agent": global_config.api.user_agent
        }

        return requests.get(met_no_api, params=parameters, headers=headers).json()
    except Exception as ex:
        print(f"Failed to get forecast: {ex}")
        return None


# Gets a forecast from the UK Met Office
@cached(cache=TTLCache(100, ttl=timedelta(minutes=10).seconds), lock=Lock())
def get_forecast_uk(lat: float, lon: float):
    try:
        parameters = {
            "dataSource": "BD1",
            "includeLocationName": True,
            "latitude": {lat},
            "longitude": {lon}
        }
        headers = {
            "accept": "application/json",
            "apikey": global_config.api.uk_met_api,
            "User-Agent": global_config.api.user_agent
        }
        pprint.pp(headers)

        return requests.get(met_uk_api, params=parameters, headers=headers).json()
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
            try:
                address = location.address
                if "suburb" in address:
                    suburb = address.suburb
                else:
                    suburb = None
                city = address.city
                state = address.state
                location.display_name = ", ".join([suburb, city, state])
            except Exception:
                # Temp work around for places that don't have cities
                pass

        rev_geocode_cache[cache_key] = location
        print(f"Reverse geocode miss for {lat}, {lon}: {location}")
    return rev_geocode_cache[cache_key]


# A very hacky way to check if a place is in the UK
# (for certain definitions that the UK definitely won't agree with)
def is_in_uk(place: str) -> bool:
    if "United Kingdom" in place:
        return True
    return False


def get_forecast(location):
    # For some reason PyCharm thinks that calling a method with a `@cached` decorator (when it has more than one
    # parameter?) is "calling" it? Until this is fixed, suppress the warning here.
    # Issue: https://youtrack.jetbrains.com/issue/PY-52210
    # noinspection PyCallingNonCallable
    if hasattr(location, "in_uk") or is_in_uk(location.display_name):
        print(f"  UK forecast from the MET")
        return get_forecast_uk(location.lat, location.lon)
    print(f"  Forecast from NO MET")
    return get_forecast_no(location.lat, location.lon)


@app.route('/place/<place>')
def place_request(place: str) -> Response:
    print(f"Request for place: {place}")
    try:
        location = geocode_place(place)
    except Exception as e:
        return jsonify({
            "error": "GEOCODE_ERROR",
            "msg": f"Failed to geocode {place}: {e}"
        })

    lat = float(location.lat)
    lon = float(location.lon)
    timezone = timezone_finder.timezone_at(lat=lat, lng=lon)
    forecast = get_forecast(location)
    return jsonify({
        "location": location,
        "timezone": timezone,
        "forecast": forecast,
    })


@app.route('/lat/<latitude>/lon/<longitude>')
def point_request(latitude: str, longitude: str) -> Response:
    lat = float(latitude)
    lon = float(longitude)
    print(f"Request for point: {lat}, {lon}")
    try:
        location = rev_geocode(lat, lon)
    except Exception as e:
        return jsonify({
            "error": "GEOCODE_ERROR",
            "msg": f"Failed to reverse-geocode {lat}, {lon}: {e}"
        })

    timezone = timezone_finder.timezone_at(lat=lat, lng=lon)
    forecast = get_forecast(location)
    return jsonify({
        "location": location,
        "timezone": timezone,
        "forecast": forecast,
    })


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

    parser = argparse.ArgumentParser(description="LilaWelt Weather API")
    parser.add_argument("--config", dest="config_path", required=True,
                        help="path to file containing custom locations")
    args = parser.parse_args()

    with open(args.config_path, "rb") as config_file:
        toml_dict = tomli.load(config_file)
    global_config = DotDict(toml_dict)

    add_locations_to_cache(global_config.locations)

    # Global geolocation object
    geolocator = Nominatim(user_agent=global_config.api.user_agent)

    # Run the Flask app
    app.run(host="0.0.0.0", port=1337)


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    main()
