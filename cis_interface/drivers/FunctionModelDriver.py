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

    def __init__(self, *args, **kwargs):
        super(FunctionModelDriver, self).__init__(*args, **kwargs)


    
    
