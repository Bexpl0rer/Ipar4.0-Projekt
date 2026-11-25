import unittest

from soil_model import (
    CAPACITY_MM,
    SIMULATION_HOURS,
    SoilState,
    advance_hour,
)


class SoilModelTests(unittest.TestCase):
    def test_initial_moisture(self):
        state = SoilState()
        self.assertEqual(state.hour, 0)
        self.assertEqual(state.water_mm, (18.0,) * 3)
        self.assertEqual(state.moisture_percent, (60.0,) * 3)

    def test_shared_valve_applies_six_litres(self):
        state = SoilState()
        step = advance_hour(state, valve_open=True)
        self.assertEqual(step.state.hour, 1)
        self.assertEqual(step.state.water_mm, (19.77, 19.76, 19.70))
        self.assertEqual(step.applied_water_l, 6)
        self.assertEqual(state.water_mm, (18.0,) * 3)

    def test_night_loss_and_next_daylight_factor(self):
        nighttime = advance_hour(SoilState(hour=12), valve_open=False)
        next_day = advance_hour(SoilState(hour=24), valve_open=False)
        self.assertEqual(nighttime.state.water_mm, (17.96, 17.96, 17.95))
        self.assertEqual(nighttime.applied_water_l, 0)
        self.assertEqual(next_day.state.water_mm, (17.8275, 17.8200, 17.7750))

    def test_water_balance_lands_exactly_on_the_threshold(self):
        state = SoilState()
        for _ in range(15):
            state = advance_hour(state, valve_open=False).state
        self.assertEqual(state.water_mm[1], 15.0)
        self.assertEqual(state.moisture_percent[1], 50.0)

    def test_storage_limits_and_applied_water(self):
        dry = advance_hour(SoilState(water_mm=(0.1,) * 3), valve_open=False)
        wet = advance_hour(SoilState(water_mm=(29.9,) * 3), valve_open=True)
        self.assertEqual(dry.state.water_mm, (0.0,) * 3)
        self.assertEqual(wet.state.water_mm, (CAPACITY_MM,) * 3)
        self.assertEqual(wet.applied_water_l, 6)

    def test_end_of_simulation(self):
        last_step = advance_hour(SoilState(hour=SIMULATION_HOURS - 1), valve_open=False)
        self.assertEqual(last_step.state.hour, 168)
        with self.assertRaisesRegex(ValueError, "simulation is complete"):
            advance_hour(last_step.state, valve_open=False)

    def test_reference_week_with_both_shared_valve_strategies(self):
        cases = (
            (15.0, False, 60, (0, 0, 52)),
            (15.0, True, 66, (0, 0, 16)),
            (16.5, False, 66, (0, 0, 15)),
            (16.5, True, 66, (0, 0, 0)),
        )
        for threshold_mm, use_average, expected_litres, expected_hours in cases:
            with self.subTest(threshold_mm=threshold_mm, use_average=use_average):
                state = SoilState()
                applied_water_l = 0.0
                outside_target_hours = [0, 0, 0]
                for _ in range(SIMULATION_HOURS):
                    for zone, water in enumerate(state.water_mm):
                        if not 12.0 <= water <= 22.5:
                            outside_target_hours[zone] += 1

                    if use_average:
                        total_mm = sum(state.water_mm)
                        valve_open = total_mm < 3 * threshold_mm
                    else:
                        valve_open = state.water_mm[1] < threshold_mm
                    step = advance_hour(state, valve_open=valve_open)
                    applied_water_l += step.applied_water_l
                    state = step.state

                self.assertEqual(applied_water_l, expected_litres)
                self.assertEqual(tuple(outside_target_hours), expected_hours)


if __name__ == "__main__":
    unittest.main()
