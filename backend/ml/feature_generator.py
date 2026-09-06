from abc import ABC, abstractmethod
from typing import List, Dict, Any
from backend.ml.feature_context import FeatureContext

class FeatureGenerator(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """The developer-friendly name of the feature generator."""
        pass

    @property
    @abstractmethod
    def feature_names(self) -> List[str]:
        """List of exact feature columns produced by this generator."""
        pass

    @property
    @abstractmethod
    def category(self) -> str:
        """Category of features generated (e.g. temporal, market)."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Semantic version of the feature generator code."""
        pass

    @abstractmethod
    def transform(self, context: FeatureContext) -> Dict[str, Any]:
        """Calculates features mapping name -> values/Series from context."""
        pass
