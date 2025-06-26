class CaptchaServiceError(Exception):
    """Basic exception for all captcha service errors"""

class NetworkConnectionError(CaptchaServiceError):
    """Network connection error"""
    
class NoValidApiKeysError(CaptchaServiceError):
    """No valid API keys"""
    
class InsufficientBalanceError(CaptchaServiceError):
    """Insufficient balance on all API keys"""
    
class TaskCreationError(CaptchaServiceError):
    """Error creating a task to solve captcha"""
    
class TaskSolutionError(CaptchaServiceError):
    """Error receiving captcha solution"""