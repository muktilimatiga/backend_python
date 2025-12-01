from services.onu_handler import OnuHandler
from services.config_handler import OltHandler

# Since both parents inherit TelnetClient, CoreHandler is a valid TelnetClient.
class CoreHandler(OnuHandler, OltHandler):
    pass