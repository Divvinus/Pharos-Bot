class WalletError(Exception):
    """
    Base class for wallet-related errors.

    Used as a parent class for all wallet-related exceptions.
    """


class InsufficientFundsError(WalletError):
    """
    Exception for insufficient funds on the wallet.

    Occurs when the wallet balance is insufficient to complete the operation.
    """
    
class BlockchainError(Exception):
    """
    Base class for blockchain-related errors.
    """