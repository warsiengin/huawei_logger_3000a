"""Register definitions and decoding for the SmartLogger SCADA guide."""

from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class Register:
    key: str
    name: str
    address: int
    data_type: str
    gain: int
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None

    @property
    def words(self) -> int:
        return 2 if self.data_type in {"u32", "i32"} else 1


@dataclass(frozen=True)
class AlarmBit:
    key: str
    name: str
    register_key: str
    bit: int


REGISTERS = (
    Register(
        "active_adjustment_volatile",
        "Active power adjustment (volatile)",
        40420,
        "u32",
        10,
        "kW",
        "power",
    ),
    Register(
        "reactive_adjustment",
        "Reactive power adjustment",
        40422,
        "i32",
        10,
        "kvar",
        "reactive_power",
    ),
    Register(
        "active_adjustment_failsafe",
        "Active power adjustment (failsafe)",
        40424,
        "u32",
        10,
        "kW",
        "power",
    ),
    Register(
        "input_power",
        "Input power",
        40521,
        "u32",
        1000,
        "kW",
        "power",
        "measurement",
    ),
    Register(
        "active_power",
        "Active power",
        40525,
        "i32",
        1000,
        "kW",
        "power",
        "measurement",
    ),
    Register(
        "power_factor",
        "Power factor",
        40532,
        "i16",
        1000,
        state_class="measurement",
    ),
    Register(
        "plant_status",
        "Plant status",
        40543,
        "u16",
        1,
        device_class="enum",
    ),
    Register(
        "reactive_power",
        "Reactive power",
        40544,
        "i32",
        1000,
        "kvar",
        "reactive_power",
        state_class="measurement",
    ),
    Register(
        "energy_total",
        "Total energy",
        40560,
        "u32",
        10,
        "kWh",
        "energy",
        "total_increasing",
    ),
    Register(
        "energy_daily",
        "Daily energy",
        40562,
        "u32",
        10,
        "kWh",
        "energy",
        "total_increasing",
    ),
    Register("alarm_info_1", "Alarm info 1", 50000, "u16", 1),
    Register("alarm_info_2", "Alarm info 2", 50001, "u16", 1),
)

ALARMS = (
    AlarmBit(
        "active_schedule_abnormal",
        "Active schedule abnormal",
        "alarm_info_1",
        3,
    ),
    AlarmBit(
        "reactive_schedule_abnormal",
        "Reactive schedule abnormal",
        "alarm_info_1",
        11,
    ),
    AlarmBit("mcb_disconnect", "MCB disconnect", "alarm_info_2", 1),
    AlarmBit("abnormal_cubicle", "Abnormal cubicle", "alarm_info_2", 2),
    AlarmBit("address_conflict", "Address conflict", "alarm_info_2", 3),
)

PLANT_STATUS = {
    1: "Unlimited",
    2: "Limited",
    3: "Idle",
    4: "Outage (fault)",
    5: "Communication interrupt",
}


def validate_slave_id(value: object) -> int:
    """Validate a Modbus unit identifier in the standard 0-247 range."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 247:
        raise ValueError("modbus_slave_id must be an integer between 0 and 247.")
    return value


def register_groups(registers: Sequence[Register] = REGISTERS) -> list[tuple[int, int]]:
    """Return contiguous (start address, word count) holding-register reads."""
    ranges = sorted(
        (register.address, register.address + register.words - 1)
        for register in registers
    )
    if not ranges:
        return []

    groups: list[tuple[int, int]] = []
    start, end = ranges[0]
    for next_start, next_end in ranges[1:]:
        if next_start <= end + 1:
            end = max(end, next_end)
            continue
        groups.append((start, end - start + 1))
        start, end = next_start, next_end
    groups.append((start, end - start + 1))
    return groups


def decode_register(register: Register, values: Mapping[int, int]) -> int | float:
    """Decode one big-endian Modbus register value and apply its gain."""
    words = [values[address] for address in range(register.address, register.address + register.words)]
    if any(not 0 <= word <= 0xFFFF for word in words):
        raise ValueError(f"Invalid 16-bit word while decoding {register.key}")

    raw = words[0] if register.words == 1 else (words[0] << 16) | words[1]
    bits = register.words * 16
    if register.data_type.startswith("i") and raw & (1 << (bits - 1)):
        raw -= 1 << bits

    if register.gain == 1:
        return raw
    return raw / register.gain


def alarm_is_active(alarm: AlarmBit, values: Mapping[str, int]) -> bool:
    """Return whether the guide's bit for an alarm is set."""
    return bool(values[alarm.register_key] & (1 << alarm.bit))
