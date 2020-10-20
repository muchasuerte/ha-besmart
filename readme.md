
# HA Riello's Besmart thermostats 

Support for Riello's Besmart thermostats.
Be aware the thermostat may require more then 3 minute to refresh its states.

The thermostats support the season switch however this control will be managed with a 
different control.

tested with home-assistant >= 0.113

Configuration example:

```yaml
climate:
  - platform: Besmart
    name: Besmart Thermostat
    username: <my-username>
    password: <my-password>
    room: Soggiorno
    scan_interval: 10

logging options:

logger:
  default: info
  logs:
    custom_components.climate.besmart: debug
```

## Contribute

Contributions are always welcome!
Please read the [contribution guidelines](contributing.md) first.

## License

[![CC0](https://licensebuttons.net/p/zero/1.0/88x31.png)](https://creativecommons.org/publicdomain/zero/1.0/)
