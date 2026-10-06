# Huawei SmartLogger MQTT add-on

This Home Assistant add-on polls the Huawei SmartLogger V300R024C10SPC161
Modbus TCP interface and publishes MQTT Discovery entities. Its register map
and protocol defaults are based on
[`docs/SmartLogger_Modbus_SCADA_Guide.pdf`](../docs/SmartLogger_Modbus_SCADA_Guide.pdf).

## Installation

1. Add `https://github.com/warsiengin/huawei_logger_3000a` as a Home Assistant
   add-on repository and install **Huawei SmartLogger MQTT**.
2. Set **Modbus host** to the SmartLogger's reachable IP address or hostname.
   The defaults are port `502` and a `10`-second polling interval.
3. Ensure the Home Assistant MQTT integration is configured, then start the
   add-on. It uses the MQTT service provided by Home Assistant and publishes
   retained MQTT Discovery configuration and state.

## Published entities

| Entity | Register | Type | Gain | Unit |
| --- | ---: | --- | ---: | --- |
| Input power | 40521 | U32 | 1000 | kW |
| Active power | 40525 | I32 | 1000 | kW |
| Power factor | 40532 | I16 | 1000 | |
| Plant status | 40543 | U16 | 1 | |
| Reactive power | 40544 | I32 | 1000 | kvar |
| Total energy | 40560 | U32 | 10 | kWh |
| Daily energy | 40562 | U32 | 10 | kWh |
| Alarm info 1 | 50000 | U16 | 1 | |
| Alarm info 2 | 50001 | U16 | 1 | |

The listed alarm bits are also exposed as binary sensors: active schedule
abnormal (alarm 1 bit 3), reactive schedule abnormal (alarm 1 bit 11), MCB
disconnect (alarm 2 bit 1), abnormal cubicle (alarm 2 bit 2), and address
conflict (alarm 2 bit 3). Plant status values follow the guide: 1 unlimited,
2 limited, 3 idle, 4 outage (fault), and 5 communication interrupt.

## Protocol and safety

- Modbus TCP, port `502`, holding-register function `0x03`, unit ID `0`.
- Register values are decoded big-endian. Multi-register 32-bit values are
  requested in a single contiguous read and scaled by dividing by the listed
  gain, as specified in the guide.
- Modbus connection/read timeout is 5 seconds. Polling is read-only: the
  writable active/reactive adjustment registers in the guide are not accessed.
- The numeric addresses are used exactly as printed in the supplied guide.
  Confirm that your SmartLogger firmware uses this address convention before
  deploying.
- MQTT availability is marked offline on read errors and online after a
  successful poll. The add-on uses retained MQTT state and discovery messages.
