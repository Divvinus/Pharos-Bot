"""
Исключения для работы с Twitter API.
"""

class TwitterClientError(Exception):
    """Базовое исключение для всех ошибок Twitter API."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class TwitterAuthError(TwitterClientError):
    """Ошибка авторизации в Twitter."""
    pass


class TwitterNetworkError(TwitterClientError):
    """Сетевая ошибка при взаимодействии с Twitter API."""
    pass


class TwitterInvalidTokenError(TwitterAuthError):
    """Недействительный или просроченный токен авторизации Twitter."""
    pass


class TwitterAccountSuspendedError(TwitterAuthError):
    """Аккаунт Twitter заблокирован или приостановлен."""
    pass


class TwitterAlreadyConnectedError(TwitterClientError):
    """Twitter-аккаунт уже привязан к кошельку."""
    def __init__(self, message: str = "Twitter account is already connected to this wallet"):
        super().__init__(message)


class TwitterRateLimitError(TwitterClientError):
    """Превышен лимит запросов к Twitter API."""
    pass


class TwitterAlreadyDoneError(TwitterClientError):
    """Действие уже было выполнено (ретвит, лайк и т.д.)."""
    pass


class TwitterActionBlockedError(TwitterClientError):
    """Действие заблокировано (например, нельзя подписаться на пользователя)."""
    pass


class TwitterAPIError(TwitterClientError):
    """Общая ошибка Twitter API."""
    def __init__(self, message: str, error_code: int = None):
        self.error_code = error_code
        super().__init__(message)