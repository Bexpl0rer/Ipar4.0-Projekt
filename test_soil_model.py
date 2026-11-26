import unittest
from random import Random

from soil_model import (
    CAPACITY_MM, SIMULATION_MINUTES, STEP_MINUTES, FLOW_L_PER_MIN,
    SoilState, advance_step, measure_moisture,
)


class SoilModelTests(unittest.TestCase):
    def test_initial_moisture(self):
        state = SoilState()
        self.assertEqual(state.minute, 0)
        self.assertEqual(state.water_mm, (18.0,) * 3)
        self.assertEqual(state.moisture_percent, (60.0,) * 3)

    def test_five_minute_water_balance(self):
        state = SoilState()
        step = advance_step(state, valve_open=True)
        self.assertEqual(step.state.minute, 5)
        self.assertEqual(step.irrigation_minutes, 5)
        self.assertEqual(step.applied_water_l, 0.5)
        for actual, loss in zip(step.state.water_mm, (0.23, 0.24, 0.30)):
            self.assertAlmostEqual(actual, 18 + (2 - loss) / 12, places=7)
        self.assertEqual(state.water_mm, (18.0,) * 3)

    def test_twelve_steps_preserve_original_hourly_rates(self):
        state = SoilState()
        litres = 0
        for _ in range(12):
            step = advance_step(state, valve_open=True)
            state = step.state
            litres += step.applied_water_l
        self.assertEqual(state.minute, 60)
        self.assertAlmostEqual(litres, 6)
        for actual, expected in zip(state.water_mm, (19.77, 19.76, 19.70)):
            self.assertAlmostEqual(actual, expected, places=6)

    def test_night_loss_and_next_daylight_factor(self):
        night = advance_step(SoilState(minute=720), valve_open=False)
        next_day = advance_step(SoilState(minute=1440), valve_open=False)
        for actual, loss in zip(night.state.water_mm, (0.04, 0.04, 0.05)):
            self.assertAlmostEqual(actual, 18 - loss / 12, places=7)
        for actual, loss in zip(next_day.state.water_mm, (0.23, 0.24, 0.30)):
            self.assertAlmostEqual(actual, 18 - 0.75 * loss / 12, places=7)
        self.assertEqual(night.applied_water_l, 0)
        self.assertEqual(night.irrigation_minutes, 0)

    def test_storage_limits_and_applied_water(self):
        dry = advance_step(SoilState(water_mm=(0.001,) * 3), valve_open=False)
        wet = advance_step(SoilState(water_mm=(29.99,) * 3), valve_open=True)
        self.assertEqual(dry.state.water_mm, (0.0,) * 3)
        self.assertEqual(wet.state.water_mm, (CAPACITY_MM,) * 3)
        self.assertEqual(wet.applied_water_l, STEP_MINUTES * FLOW_L_PER_MIN)

    def test_end_of_simulation_and_grid(self):
        last_step = advance_step(SoilState(minute=SIMULATION_MINUTES - STEP_MINUTES),
                                 valve_open=False)
        self.assertEqual(last_step.state.minute, 10080)
        with self.assertRaisesRegex(ValueError, "simulation is complete"):
            advance_step(last_step.state, valve_open=False)
        with self.assertRaises(ValueError):
            SoilState(minute=1)

    def test_noise_bounds_and_reproducibility(self):
        state = SoilState()
        first, second = Random(42), Random(42)
        changed = False
        for _ in range(20):
            measured = measure_moisture(state, first, 0.5)
            self.assertEqual(measured, measure_moisture(state, second, 0.5))
            for value in measured:
                self.assertLessEqual(abs(value - 60), 0.5)
                changed |= value != 60
        self.assertTrue(changed)
        self.assertEqual(measure_moisture(state, Random(42), 0), state.moisture_percent)
        self.assertEqual(state.water_mm, (18.0,) * 3)

    def test_noise_clipped_at_physical_limits(self):
        state = SoilState(water_mm=(0.0, 30.0, 0.0))
        rng = Random(7)
        for _ in range(20):
            self.assertTrue(all(0 <= x <= 100 for x in measure_moisture(state, rng, 1)))
        with self.assertRaises(ValueError):
            measure_moisture(state, rng, -1)


if __name__ == "__main__":
    unittest.main()
