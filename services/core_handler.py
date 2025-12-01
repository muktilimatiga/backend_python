# services/master_handler.py
from services.onu_handler import OnuHandler
from services.config_handler import OltHandler

# Multiple Inheritance:
# This class now has access to:
# 1. connect() from TelnetBase (via OnuHandler/ConfigHandler)
# 2. get_onu_detail() from OnuHandler
# 3. apply_configuration() from ConfigHandler

class CoreHandler(OnuHandler, OltHandler):
    pass