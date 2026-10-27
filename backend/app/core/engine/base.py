"""Core simulation abstractions: models, events, snapshots. No IO dependencies."""

ENGINE_VERSION = "1.0"


class ModelType:
    TIME_STEPPED = "time_stepped"
    DISCRETE_EVENT = "discrete_event"


class SimulationError(RuntimeError):
    pass


class SimulationLimitExceeded(SimulationError):
    def __init__(self, message: str, limit: str):
        super().__init__(message)
        self.limit = limit


class SimulationCancelled(SimulationError):
    pass
