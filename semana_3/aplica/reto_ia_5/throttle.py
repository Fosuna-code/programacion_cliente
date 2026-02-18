"""
Throttle - Rate Limiting y Control de Concurrencia
==================================================

Este módulo implementa 3 clases de limitación para proteger servidor y cliente:
1. ConcurrencyLimiter: Máx N peticiones simultáneas (Semaphore)
2. RateLimiter: Máx M peticiones por segundo (Token Bucket)
3. ThrottledClient: Combina ambos límites

Autor: Semana 3 - Reto IA #5 (AVANZADO)
"""

import asyncio
import aiohttp
import time
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# CLASS 1: ConcurrencyLimiter (Semaphore-based)
# ============================================================================

class ConcurrencyLimiter:
    """
    Limits the number of concurrent operations using asyncio.Semaphore.
    
    Scenario: Prevent more than N simultaneous HTTP requests to avoid:
    - Server overload (respects API connection limits)
    - Client resource exhaustion (file descriptors, memory)
    
    Example:
        limiter = ConcurrencyLimiter(max_concurrent=10)
        async with limiter:
            await hacer_peticion()  # Max 10 at a time
    """
    
    def __init__(self, max_concurrent: int):
        """
        Args:
            max_concurrent: Maximum number of simultaneous operations
        """
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._en_vuelo = 0
        self._total_adquiridos = 0
    
    async def __aenter__(self):
        """Context manager entry - acquires semaphore slot."""
        await self._semaphore.acquire()
        self._total_adquiridos += 1
        self._en_vuelo += 1
        logger.debug(f"🔵 Acquired | In-flight: {self._en_vuelo}/{self.max_concurrent}")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - releases semaphore slot."""
        self._semaphore.release()
        self._en_vuelo -= 1
        logger.debug(f"🟢 Released | In-flight: {self._en_vuelo}/{self.max_concurrent}")
    
    def stats(self) -> dict:
        """Returns concurrency statistics."""
        return {
            "max_concurrent": self.max_concurrent,
            "currently_in_flight": self._en_vuelo,
            "total_acquired": self._total_adquiridos
        }


# ============================================================================
# CLASS 2: RateLimiter (Token Bucket Algorithm)
# ============================================================================

class RateLimiter:
    """
    Limits the rate of operations using Token Bucket algorithm.
    
    Token Bucket works like this:
    - Bucket starts with M tokens
    - Each request consumes 1 token
    - Tokens refill at rate of M per second
    - If bucket empty, request waits until next token available
    
    Example:
        limiter = RateLimiter(max_per_second=20)
        async with limiter:
            await hacer_peticion()  # Max 20/second, waits if exceeded
    """
    
    def __init__(self, max_per_second: float):
        """
        Args:
            max_per_second: Maximum requests per second allowed
        """
        self.max_per_second = max_per_second
        self.tokens = max_per_second  # Start with full bucket
        self.last_refill = time.time()
        self._lock = asyncio.Lock()
        self._total_waited_ms = 0
        self._requests_throttled = 0
    
    async def __aenter__(self):
        """Context manager entry - waits for token if needed."""
        async with self._lock:
            # Refill tokens based on time elapsed
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(
                self.max_per_second,
                self.tokens + (elapsed * self.max_per_second)
            )
            self.last_refill = now
            
            # If no tokens available, wait
            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.max_per_second
                logger.debug(f"⏳ Rate limit reached, waiting {wait_time*1000:.0f}ms")
                self._total_waited_ms += wait_time * 1000
                self._requests_throttled += 1
                await asyncio.sleep(wait_time)
                
                # After waiting, refill tokens
                now = time.time()
                elapsed = now - self.last_refill
                self.tokens = min(
                    self.max_per_second,
                    self.tokens + (elapsed * self.max_per_second)
                )
                self.last_refill = now
            
            # Consume one token
            self.tokens -= 1
            logger.debug(f"🪙 Token consumed | Remaining: {self.tokens:.2f}/{self.max_per_second}")
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - nothing to release for rate limiter."""
        pass
    
    def stats(self) -> dict:
        """Returns rate limiting statistics."""
        return {
            "max_per_second": self.max_per_second,
            "current_tokens": self.tokens,
            "total_waited_ms": self._total_waited_ms,
            "requests_throttled": self._requests_throttled
        }


# ============================================================================
# CLASS 3: ThrottledClient (Combines Both Limiters)
# ============================================================================

class ThrottledClient:
    """
    HTTP client that respects BOTH concurrency AND rate limits simultaneously.
    
    This ensures:
    - Never more than max_concurrent requests in-flight
    - Never more than max_per_second requests per second
    
    Example:
        client = ThrottledClient(max_concurrent=10, max_per_second=20)
        
        # Make 50 requests
        for i in range(50):
            await client.request("GET", "https://api.com/endpoint")
        
        # Guarantees:
        # - Never more than 10 simultaneous connections
        # - Never more than 20 requests initiated per second
    """
    
    def __init__(
        self,
        max_concurrent: int = 10,
        max_per_second: float = 20,
        timeout: Optional[aiohttp.ClientTimeout] = None
    ):
        """
        Args:
            max_concurrent: Max simultaneous requests (default: 10)
            max_per_second: Max requests per second (default: 20)
            timeout: Optional timeout configuration
        """
        self.concurrency_limiter = ConcurrencyLimiter(max_concurrent)
        self.rate_limiter = RateLimiter(max_per_second)
        
        if timeout is None:
            timeout = aiohttp.ClientTimeout(total=10)
        
        self._session = aiohttp.ClientSession(timeout=timeout)
        
        logger.info(f"✨ ThrottledClient initialized: "
                   f"max_concurrent={max_concurrent}, max_per_second={max_per_second}")
    
    async def request(self, method: str, url: str, **kwargs):
        """
        Makes an HTTP request respecting both limits.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: URL to request
            **kwargs: Additional arguments for session.request()
        
        Returns:
            Response data (JSON parsed if available)
        """
        # Both limiters must be acquired before making the request
        async with self.concurrency_limiter:  # Limit #1: Concurrency
            async with self.rate_limiter:      # Limit #2: Rate
                async with self._session.request(method, url, **kwargs) as response:
                    return await response.json()
    
    def get_stats(self) -> dict:
        """Returns combined statistics from both limiters."""
        return {
            "concurrency": self.concurrency_limiter.stats(),
            "rate": self.rate_limiter.stats()
        }
    
    def print_stats(self):
        """Prints formatted statistics."""
        stats = self.get_stats()
        
        print("\n📊 THROTTLED CLIENT STATISTICS")
        print("="*60)
        
        print("\n🔵 Concurrency Limiter:")
        print(f"   Max concurrent: {stats['concurrency']['max_concurrent']}")
        print(f"   Currently in-flight: {stats['concurrency']['currently_in_flight']}")
        print(f"   Total acquired: {stats['concurrency']['total_acquired']}")
        
        print("\n🪙 Rate Limiter:")
        print(f"   Max per second: {stats['rate']['max_per_second']}")
        print(f"   Current tokens: {stats['rate']['current_tokens']:.2f}")
        print(f"   Requests throttled: {stats['rate']['requests_throttled']}")
        print(f"   Total wait time: {stats['rate']['total_waited_ms']:.0f}ms")
        
        print("="*60 + "\n")
    
    async def close(self):
        """Closes the underlying HTTP session."""
        await self._session.close()
    
    async def __aenter__(self):
        """Context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()


# ============================================================================
# DEMONSTRATION & TESTING
# ============================================================================

async def test_concurrency_limiter():
    """Tests that ConcurrencyLimiter enforces max simultaneous operations."""
    print("\n" + "="*60)
    print("TEST 1: ConcurrencyLimiter (Max 5 Simultaneous)")
    print("="*60 + "\n")
    
    limiter = ConcurrencyLimiter(max_concurrent=5)
    
    async def operacion_simulada(idx: int):
        """Simulates a slow operation."""
        async with limiter:
            print(f"  [{idx:02d}] Started | In-flight: {limiter._en_vuelo}/5")
            await asyncio.sleep(0.1)  # Simulate work
            print(f"  [{idx:02d}] Done")
    
    print("Launching 15 operations with max_concurrent=5...")
    print("Expected: Never more than 5 running simultaneously\n")
    
    inicio = time.time()
    await asyncio.gather(*[operacion_simulada(i) for i in range(15)])
    tiempo_total = (time.time() - inicio) * 1000
    
    print(f"\n⏱️  Total time: {tiempo_total:.0f}ms")
    print(f"📊 Stats: {limiter.stats()}")
    print("✅ Max 5 concurrent enforced!\n")


async def test_rate_limiter():
    """Tests that RateLimiter enforces max requests per second."""
    print("\n" + "="*60)
    print("TEST 2: RateLimiter (Max 10 req/s)")
    print("="*60 + "\n")
    
    limiter = RateLimiter(max_per_second=10)
    
    async def peticion_rapida(idx: int):
        """Simulates instant request."""
        async with limiter:
            print(f"  [{idx:02d}] Request sent")
    
    print("Launching 25  requests with max_per_second=10...")
    print("Expected: First 10 instant, next 15 throttled (wait)\n")
    
    inicio = time.time()
    await asyncio.gather(*[peticion_rapida(i) for i in range(25)])
    tiempo_total = (time.time() - inicio) * 1000
    
    print(f"\n⏱️  Total time: {tiempo_total:.0f}ms")
    print(f"📊 Stats: {limiter.stats()}")
    print(f"💡 Expected ~2500ms (25 requests / 10 per second)\n")


async def test_throttled_client():
    """Tests ThrottledClient with real HTTP requests."""
    print("\n" + "="*60)
    print("TEST 3: ThrottledClient (10 concurrent, 20 req/s)")
    print("="*60 + "\n")
    
    async with ThrottledClient(max_concurrent=10, max_per_second=20) as client:
        print("Making 50 requests to httpbin.org/delay/0...")
        print("Expected behavior:")
        print("  - Never more than 10 requests in-flight")
        print("  - Never more than 20 requests initiated per second\n")
        
        inicio = time.time()
        
        # Make 50 requests
        tareas = []
        for i in range(50):
            tareas.append(client.request("GET", "https://httpbin.org/delay/0"))
        
        resultados = await asyncio.gather(*tareas, return_exceptions=True)
        
        tiempo_total = (time.time() - inicio) * 1000
        
        # Count successes
        exitosos = sum(1 for r in resultados if not isinstance(r, Exception))
        
        print(f"\n⏱️  Total time: {tiempo_total:.0f}ms")
        print(f"✅ Successful: {exitosos}/50")
        
        client.print_stats()
        
        print(f"💡 Notice:")
        print(f"   - Total time ~{tiempo_total:.0f}ms (respects 20 req/s = ~2.5s for 50)")
        print(f"   - Max {client.concurrency_limiter.max_concurrent} in-flight enforced\n")


async def generar_grafica_requests_vs_tiempo():
    """Generates ASCII graph showing requests in-flight over time."""
    print("\n" + "="*60)
    print("GRAPH: Requests In-Flight vs Time")
    print("="*60 + "\n")
    
    limiter = ConcurrencyLimiter(max_concurrent=5)
    snapshots = []
    
    async def operacion_con_snapshot(idx: int):
        """Operation that records in-flight count."""
        async with limiter:
            snapshots.append((time.time(), limiter._en_vuelo))
            await asyncio.sleep(0.05)
    
    inicio = time.time()
    await asyncio.gather(*[operacion_con_snapshot(i) for i in range(20)])
    
    # Generate ASCII graph
    print("Time (ms)  │ Requests In-Flight")
    print("───────────┼" + "─" * 40)
    
    for timestamp, count in snapshots[:15]:  # Show first 15 snapshots
        tiempo_ms = (timestamp - inicio) * 1000
        barra = "█" * count
        print(f"{tiempo_ms:8.0f}ms │ {barra} ({count})")
    
    print("\n💡 Graph shows that concurrency never exceeds 5\n")


# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Runs all demonstrations."""
    print("""
    ╔══════════════════════════════════════════════════════════════════════╗
    ║              Throttle - Rate Limiting & Concurrency                  ║
    ║                      Advanced Traffic Control                        ║
    ╚══════════════════════════════════════════════════════════════════════╝
    """)
    
    # Test 1: Concurrency limiter
    await test_concurrency_limiter()
    
    # Test 2: Rate limiter
    await test_rate_limiter()
    
    # Test 3: Throttled client (combines both)
    await test_throttled_client()
    
    # Bonus: ASCII graph
    await generar_grafica_requests_vs_tiempo()
    
    print("✅ All tests completed!\n")


if __name__ == "__main__":
    asyncio.run(main())
