import importlib
import pkgutil
import logging
from typing import List, Type

from backend.firewall.guardrails.base import BaseGuardrail
from backend.firewall.config import FirewallConfig
import backend.firewall.guardrails

logger = logging.getLogger(__name__)

class GuardrailDiscovery:
    """Dynamically discovers all guardrails inheriting from BaseGuardrail."""
    
    @classmethod
    def discover(cls, config: FirewallConfig) -> List[BaseGuardrail]:
        """
        Iterates over the firewall.guardrails module and instantiates 
        any subclass of BaseGuardrail it finds.
        """
        guardrails = []
        
        # Iterating through all modules in the firewall.guardrails package
        package = backend.firewall.guardrails
        for _, module_name, is_pkg in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
            try:
                importlib.import_module(module_name)
            except Exception as e:
                logger.warning(f"Failed to import {module_name} during discovery: {e}")
                
        # Now find all subclasses
        for subclass in BaseGuardrail.__subclasses__():
            try:
                instance = subclass(config)
                guardrails.append(instance)
                logger.debug(f"Discovered and initialized guardrail: {subclass.__name__} ('{instance.name}')")
            except Exception as e:
                logger.error(f"Failed to initialize guardrail {subclass.__name__}: {e}")
                
        logger.info(f"Dynamically discovered {len(guardrails)} guardrails.")
        return guardrails
