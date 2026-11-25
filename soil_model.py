"""Hourly water balance for a three-zone greenhouse bed with one valve."""

from dataclasses import dataclass
from decimal import Decimal


CAPACITY_MM = Decimal("30")
INITIAL_WATER_MM = Decimal("18")
ZONE_AREA_M2 = Decimal("1")
IRRIGATION_DEPTH_MM = Decimal("2")
DAYTIME_LOSS_MM = (Decimal("0.23"), Decimal("0.24"), Decimal("0.30"))
NIGHTTIME_LOSS_MM = (Decimal("0.04"), Decimal("0.04"), Decimal("0.05"))
DAYLIGHT_FACTORS = (
    Decimal("1.00"),
    Decimal("0.75"),
    Decimal("0.65"),
    Decimal("1.00"),
    Decimal("1.10"),
    Decimal("1.05"),
    Decimal("0.80"),
)
SIMULATION_HOURS = 24 * len(DAYLIGHT_FACTORS)


@dataclass(frozen=True)
class SoilState:
    """Water stored in each zone at the start of the given elapsed hour."""

    hour: int = 0
    water_mm: tuple[Decimal, ...] = (INITIAL_WATER_MM,) * len(DAYTIME_LOSS_MM)

    def __post_init__(self) -> None:
        if not 0 <= self.hour <= SIMULATION_HOURS:
            raise ValueError(f"Hour must be between 0 and {SIMULATION_HOURS}")
        if len(self.water_mm) != len(DAYTIME_LOSS_MM):
            raise ValueError("The greenhouse bed has three zones")
        if any(
            not water.is_finite() or not 0 <= water <= CAPACITY_MM
            for water in self.water_mm
        ):
            raise ValueError(f"Zone water must be between 0 and {CAPACITY_MM} mm")

    @property
    def moisture_percent(self) -> tuple[Decimal, ...]:
        """Percentage of the modelled storage capacity in each zone."""
        return tuple(water * 100 / CAPACITY_MM for water in self.water_mm)


@dataclass(frozen=True)
class SoilStep:
    state: SoilState
    applied_water_l: Decimal


def advance_hour(state: SoilState, *, valve_open: bool) -> SoilStep:
    """Apply the shared valve command and one hour of water loss."""
    if state.hour == SIMULATION_HOURS:
        raise ValueError("The seven-day simulation is complete")

    day, hour_in_day = divmod(state.hour, 24)
    # Each model day starts at 07:00, with daylight until 19:00.
    if hour_in_day < 12:
        loss_mm = tuple(loss * DAYLIGHT_FACTORS[day] for loss in DAYTIME_LOSS_MM)
    else:
        loss_mm = NIGHTTIME_LOSS_MM

    added_mm = IRRIGATION_DEPTH_MM if valve_open else Decimal("0")
    next_water_mm = tuple(
        min(CAPACITY_MM, max(Decimal("0"), water - loss + added_mm))
        for water, loss in zip(state.water_mm, loss_mm)
    )
    return SoilStep(
        state=SoilState(hour=state.hour + 1, water_mm=next_water_mm),
        applied_water_l=added_mm * ZONE_AREA_M2 * len(next_water_mm),
    )
