"""SMS boundary. No delivery is simulated when a real provider is absent."""
from .config import settings

class SmsUnavailableError(RuntimeError): pass

def sms_available() -> bool:
    return settings.sms_provider != 'none'

def send_verification_code(recipient: str, code: str) -> None:
    # Add a real provider implementation and credentials before enabling this path.
    raise SmsUnavailableError('SMS delivery is not configured')
