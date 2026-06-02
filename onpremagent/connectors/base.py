import logging
from abc import ABC, abstractmethod

from onpremagent.types.firewall_rule import FirewallRule


class BaseConnector[ST](ABC):
    def __init__(self, settings: ST) -> None:
        self.settings = settings

        self.logger = logging.getLogger(
            f"onpremagent.connectors.{self.__class__.__name__}"
        )

    @abstractmethod
    def add_firewall_rule(self, rule: FirewallRule) -> None: ...

    @abstractmethod
    def remove_firewall_rule(self, rule_id: str) -> None: ...

    @abstractmethod
    def list_firewall_rules(self) -> list[FirewallRule]: ...

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...
