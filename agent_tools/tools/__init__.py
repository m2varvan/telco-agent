# Register all custom NAT tools by importing them here.
# The @register_function decorators execute on import.
from agent_tools.tools import query_lte_kpi  # noqa: F401
from agent_tools.tools import query_nr_endc  # noqa: F401
from agent_tools.tools import query_cm_config  # noqa: F401
from agent_tools.tools import query_alarm_history  # noqa: F401
from agent_tools.tools import query_neighbour_topology  # noqa: F401
from agent_tools.tools import query_kpi_trend  # noqa: F401
from agent_tools.tools import query_similar_incidents  # noqa: F401
from agent_tools.tools import query_telecom_knowledge  # noqa: F401

