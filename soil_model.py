"""Five-minute water balance for a three-zone greenhouse bed."""

from dataclasses import dataclass
from random import Random

CAPACITY_MM = 30.0
INITIAL_WATER_MM = 18.0
ZONE_AREA_M2 = 1.0
ZONE_COUNT = 3
STEP_MINUTES = 5
FLOW_L_PER_MIN = 0.1  # 6 L/hour for the whole bed
DAYTIME_LOSS_MM = (0.23, 0.24, 0.30)  # mm/hour
NIGHTTIME_LOSS_MM = (0.04, 0.04, 0.05)  # mm/hour
DAYLIGHT_FACTORS = (1.00, 0.75, 0.65, 1.00, 1.10, 1.05, 0.80)
SIMULATION_HOURS = 24 * len(DAYLIGHT_FACTORS)
SIMULATION_MINUTES = SIMULATION_HOURS * 60
WATER_PRECISION = 8
DEFAULT_NOISE_PP = 0.5
DEFAULT_SEED = 42


@dataclass(frozen=True)
class SoilState:
    """Stored water at the start of the elapsed model minute."""

    minute: int = 0
    water_mm: tuple[float, ...] = (INITIAL_WATER_MM,) * ZONE_COUNT

    def __post_init__(self) -> None:
        if (type(self.minute) is not int or not 0 <= self.minute <= SIMULATION_MINUTES
                or self.minute % STEP_MINUTES):
            raise ValueError("Minute must be on the five-minute simulation grid")
        if len(self.water_mm) != ZONE_COUNT:
            raise ValueError("The greenhouse bed has three zones")
        if any(not 0 <= water <= CAPACITY_MM for water in self.water_mm):
            raise ValueError(f"Zone water must be between 0 and {CAPACITY_MM} mm")

    @property
    def moisture_percent(self) -> tuple[float, ...]:
        """Percentage of the modelled storage capacity, not volumetric moisture."""
        return tuple(water * 100 / CAPACITY_MM for water in self.water_mm)


@dataclass(frozen=True)
class SoilStep:
    state: SoilState
    applied_water_l: float
    irrigation_minutes: int


def measure_moisture(state: SoilState, rng: Random, noise_pp: float = DEFAULT_NOISE_PP):
    """Draw one independent bounded error per zone, even in single-sensor mode."""
    if not 0 <= noise_pp <= 100:
        raise ValueError("Noise amplitude must be between 0 and 100 percentage points")
    return tuple(min(100.0, max(0.0, value + rng.uniform(-noise_pp, noise_pp)))
                 for value in state.moisture_percent)


def advance_step(state: SoilState, *, valve_open: bool) -> SoilStep:
    """Apply five model minutes of loss and flow through the shared valve."""
    if state.minute == SIMULATION_MINUTES:
        raise ValueError("The seven-day simulation is complete")

    day, minute_in_day = divmod(state.minute, 24 * 60)
    # Model day starts at 07:00; daylight ends at 19:00.
    if minute_in_day < 12 * 60:
        loss_rate = tuple(loss * DAYLIGHT_FACTORS[day] for loss in DAYTIME_LOSS_MM)
    else:
        loss_rate = NIGHTTIME_LOSS_MM

    irrigation_minutes = STEP_MINUTES if valve_open else 0
    applied_water_l = irrigation_minutes * FLOW_L_PER_MIN
    added_mm = applied_water_l / (ZONE_AREA_M2 * ZONE_COUNT)
    next_water_mm = tuple(
        min(CAPACITY_MM, max(0.0, round(
            water - loss * STEP_MINUTES / 60 + added_mm, WATER_PRECISION)))
        for water, loss in zip(state.water_mm, loss_rate)
    )
    return SoilStep(
        state=SoilState(minute=state.minute + STEP_MINUTES, water_mm=next_water_mm),
        applied_water_l=applied_water_l,
        irrigation_minutes=irrigation_minutes,
    )
