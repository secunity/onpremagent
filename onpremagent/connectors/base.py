import logging
from abc import ABC
from typing import Any

from onpremagent.types.firewall_rule import FirewallRule


class BaseConnector[ST](ABC):
    """Abstract base class for firewall connectors.

    A connector adapts a specific firewall backend to a common interface used
    by the agent: managing firewall rules and retrieving statistics. Concrete
    subclasses implement the backend-specific behaviour by overriding the rule
    and statistics methods, and may optionally override the connection and
    lifecycle hooks.

    The type parameter ``ST`` is the settings type accepted by the connector,
    allowing each subclass to declare its own strongly typed settings.
    """

    def __init__(self, settings: ST) -> None:
        """Initialize the connector.

        Args:
            settings: Backend-specific configuration for this connector.
        """
        self.settings = settings

        self.logger = logging.getLogger(
            f"onpremagent.connectors.{self.__class__.__name__}"
        )

    def add_firewall_rule(self, rule: FirewallRule) -> None:
        """Add a firewall rule to the backend.

        Args:
            rule: The firewall rule to add.
        """
        raise NotImplementedError

    def remove_firewall_rule(self, rule_id: str) -> None:
        """Remove a firewall rule from the backend.

        Args:
            rule_id: Identifier of the firewall rule to remove.
        """
        raise NotImplementedError

    def list_firewall_rules(self) -> list[FirewallRule]:
        """Return the firewall rules currently configured on the backend.

        Returns:
            The list of firewall rules.
        """
        raise NotImplementedError

    def get_raw_statistics(self) -> Any:
        """Return raw, backend-specific statistics.

        Returns:
            The statistics in whatever format the backend provides.
        """
        raise NotImplementedError

    def connect(self) -> None:
        """Establish a connection to the backend."""
        pass

    def disconnect(self) -> None:
        """Close the connection to the backend."""
        pass

    def setup(self) -> None:
        """Perform any one-time setup before the connector is used."""
        pass

    def cleanup(self) -> None:
        """Release resources held by the connector."""
        pass
