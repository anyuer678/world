"""Built-in model plugins. Importing a package registers its models.
New models: add one import line here - no core module changes needed."""
from . import cache_sim  # noqa: F401
from . import cellular_automaton  # noqa: F401
from . import cpu_scheduling  # noqa: F401
from . import queueing  # noqa: F401
from . import schelling  # noqa: F401
from . import traffic_network  # noqa: F401
