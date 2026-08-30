class VerificationBudgetGate:
    """Implements the τ threshold from Framework §6."""
    
    def __init__(self, tau: float = 0.6):
        self.tau = tau
    
    def should_verify(self, eta: float) -> bool:
        """Only verify if η ≥ τ."""
        return eta >= self.tau
