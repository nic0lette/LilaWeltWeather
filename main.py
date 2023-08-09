from collections import namedtuple
from datetime import timedelta
from threading import Lock

import requests
from cachetools import LRUCache, cached, TTLCache
from timezonefinder import TimezoneFinder
from config import USER_AGENT

geocoder_url = "https://geocode.maps.co/search"
weather_url = "https://api.met.no/weatherapi/locationforecast/2.0/complete.json"

headers = {
    "User-Agent": USER_AGENT
}

# Global shared instance for converting lat/lon to a timezone
timezone_finder = TimezoneFinder()

# Type for passing around place data (lat, lon, and timezone)
PlaceData = namedtuple("PlaceData", "lat lon tz")


@cached(cache=LRUCache(maxsize=1000), lock=Lock())
def geocode_place(place: str) -> PlaceData:
    parameters = {
        "q": {place}
    }
    location_response = requests.get(geocoder_url, params=parameters, headers=headers).json()[0]
    lat = location_response["lat"]
    lon = location_response["lon"]
    tz = timezone_finder.timezone_at(lng=float(lon), lat=float(lat))
    return PlaceData(lat=lat, lon=lon, tz=tz)


@cached(cache=TTLCache(100, ttl=timedelta(minutes=10).seconds), lock=Lock())
def get_forecast_(lat: str, lon: str):
    try:
        parameters = {
            "lat": {lat},
            "lon": {lon}
        }
        forecast = requests.get(weather_url, params=parameters, headers=headers).json()
        return forecast
    except Exception:
        return None


def get_forecast(location: PlaceData):
    # For some reason PyCharm thinks that calling a method with a `@cached` decorator (when it has more than one
    # parameter?) is "calling" it? Until this is fixed, suppress the warning here.
    # Issue: https://youtrack.jetbrains.com/issue/PY-52210
    # noinspection PyCallingNonCallable
    return get_forecast_(location.lat, location.lon)


def main():
    tokyo = geocode_place("Tokyo")
    forecast = get_forecast(location=tokyo)
    print(f"Forecast: {forecast}")


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    main()
