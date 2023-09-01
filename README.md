# LilaWeltWeather

MQTT Weather forecast API

## Usage

To use this, create a file named `config.py` in the form:

```python
USER_AGENT = "User-Agent for met.no (email/project/etc)"

MQTT = {
    "broker": "server.address",
    "port": 1234,
    "user": "user",
    "password": "password"
}
```

Guidance for the value of `USER_AGENT` can be found on https://api.met.no/doc/FAQ.