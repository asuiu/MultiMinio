try:
    from .local_config import BaseConfig
except ImportError:
    from .base_config import BaseConfig
CONFIG = BaseConfig
