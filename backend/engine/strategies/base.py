"""Base Strategy Interface."""

from abc import ABC, abstractmethod
from backend.app.models import QueryRequest, QueryResponse


class BaseStrategy(ABC):
    """Abstract Strategy interface for Cache Arena and pipeline executions."""

    @abstractmethod
    def handle(self, req: QueryRequest) -> QueryResponse:
        """Process incoming query request according to the strategy rules."""
        pass

