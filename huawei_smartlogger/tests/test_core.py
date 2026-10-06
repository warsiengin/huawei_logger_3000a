import unittest

from core import (
    ALARMS,
    REGISTERS,
    Register,
    alarm_is_active,
    decode_register,
    register_groups,
    validate_slave_id,
)


class RegisterDecodingTests(unittest.TestCase):
    def test_decodes_unsigned_32_bit_big_endian_with_gain(self) -> None:
        register = Register("energy", "Energy", 100, "u32", 10)
        self.assertEqual(decode_register(register, {100: 0x0001, 101: 0x86A0}), 10000)

    def test_decodes_signed_32_bit_big_endian_with_gain(self) -> None:
        register = Register("power", "Power", 200, "i32", 1000)
        self.assertEqual(
            decode_register(register, {200: 0xFFFF, 201: 0xFC18}),
            -1,
        )

    def test_decodes_signed_16_bit(self) -> None:
        register = Register("factor", "Factor", 10, "i16", 1000)
        self.assertEqual(decode_register(register, {10: 0xFC18}), -1)

    def test_groups_contiguous_words_into_atomic_reads(self) -> None:
        self.assertEqual(
            register_groups(),
            [
                (40521, 2),
                (40525, 2),
                (40532, 1),
                (40543, 3),
                (40560, 4),
                (50000, 2),
            ],
        )

    def test_alarm_bit_is_read_from_its_documented_register(self) -> None:
        alarm = next(item for item in ALARMS if item.key == "mcb_disconnect")
        self.assertTrue(alarm_is_active(alarm, {"alarm_info_2": 1 << 1}))
        self.assertFalse(alarm_is_active(alarm, {"alarm_info_2": 0}))

    def test_all_documented_registers_fit_the_defined_wire_range(self) -> None:
        for register in REGISTERS:
            self.assertGreaterEqual(register.address, 0)
            self.assertLessEqual(register.address + register.words - 1, 0xFFFF)

    def test_slave_id_accepts_default_and_broadcast_boundary(self) -> None:
        self.assertEqual(validate_slave_id(0), 0)
        self.assertEqual(validate_slave_id(247), 247)

    def test_slave_id_rejects_out_of_range_and_non_integer_values(self) -> None:
        for value in (-1, 248, True, "1", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_slave_id(value)


if __name__ == "__main__":
    unittest.main()
