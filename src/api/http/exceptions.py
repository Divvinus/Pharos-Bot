class APIClientError(Exception):
    """Base exception for all API client errors"""
    
class APIConnectionError(APIClientError):
    """Error when connecting to the API"""
    
class APITimeoutError(APIClientError):
    """Timeout when making API request"""
    
class APIRateLimitError(APIClientError):
    """API rate limit exceeded"""
    
class APIResponseError(APIClientError):
    """Error in API response"""
        
class APIClientSideError(APIResponseError):
    """Client-side error (4xx)"""
    
class APIServerSideError(APIResponseError):
    """Server-side error (5xx)"""
    
class APISessionError(APIClientError):
    """Error related to API session"""
    
class APISSLError(APIConnectionError):
    """SSL error during API request""" 