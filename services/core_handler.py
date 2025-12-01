# services/core_handler.py
from services.onu_handler import OnuHandler
from services.config_handler import OltHandler

# Multiple Inheritance:
# This class now has access to:
# 1. connect(), execute_command() from TelnetClient (the grandparent)
# 2. get_onu_detail() from OnuHandler
# 3. apply_configuration() from OltHandler

class CoreHandler(OnuHandler, OltHandler):
    pass