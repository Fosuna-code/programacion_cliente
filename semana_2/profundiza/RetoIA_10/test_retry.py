import unittest
from unittest.mock import patch, MagicMock

class MockResponse:
    def __init__(self, status_code, reason):
        self.status_code = status_code
        self.reason = reason

class MockHTTPError(Exception):
    def __init__(self, status_code, reason):
        self.response = MockResponse(status_code, reason)
        super().__init__(f"{status_code}: {reason}")

from retry import with_retry

class TestRetrySystem(unittest.TestCase):
    
    @patch('time.sleep') # Mockeamos sleep para que los tests sean instantáneos
    def test_retry_on_5xx(self, mock_sleep):
        """Debe reintentar 2 veces y tener éxito en la tercera"""
        mock_func = MagicMock()
        mock_func.__name__ = "mock_func"
        mock_func.side_effect = [
            MockHTTPError(500, "Error"), # Intento 1: Falla
            MockHTTPError(502, "Bad Gateway"), # Intento 2: Falla
            "Success" # Intento 3: Éxito
        ]
        
        # Decoramos el mock
        decorated = with_retry(max_retries=3)(mock_func)
        result = decorated()
        
        self.assertEqual(result, "Success")
        self.assertEqual(mock_func.call_count, 3) # Se llamó 3 veces
        self.assertEqual(mock_sleep.call_count, 2) # Se esperó 2 veces

    @patch('time.sleep')
    def test_no_retry_on_4xx(self, mock_sleep):
        """Debe fallar INMEDIATAMENTE en error 400"""
        mock_func = MagicMock()
        mock_func.__name__ = "mock_func"
        mock_func.side_effect = MockHTTPError(401, "Unauthorized")
        
        decorated = with_retry(max_retries=5)(mock_func)
        
        with self.assertRaises(MockHTTPError):
            decorated()
            
        self.assertEqual(mock_func.call_count, 1) # Solo 1 intento
        mock_sleep.assert_not_called() # No hubo espera

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)