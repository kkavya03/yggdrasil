from cis_interface.drivers.ModelDriver import ModelDriver
from cis_interface.schema import register_component


@register_component
class FunctionModelDriver(ModelDriver):
    r"""Class that acts as a functional interface to input/output channels
    that are not connected.

    Args:

    Attributes:

    """

    _language = 'function'

    def before_start(self):
        r"""Actions to perform before the run starts."""
        pass

    def before_loop(self):
        r"""Actions before loop."""
        pass

    def run_loop(self):
        r"""Loop to check if model is still running and forward output."""
        pass
