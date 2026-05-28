"""
run_demo.py — Ejecuta el demo integrado con el servidor mock en segundo plano.
Genera demo_resiliencia.log automaticamente.

Uso: python run_demo.py
"""

import subprocess
import sys
import time
import signal
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVIDOR_PATH = os.path.join(BASE_DIR, "servidor_mock.py")
CLIENTE_PATH = os.path.join(BASE_DIR, "cliente_integrado.py")
LOG_PATH = os.path.join(BASE_DIR, "demo_resiliencia.log")


def main():
    print("=" * 60)
    print("  EcoMarket — Grand Deploy Demo Runner")
    print("=" * 60)

    # 1. Iniciar servidor mock
    print("\n[1/3] Iniciando servidor mock...")
    servidor = subprocess.Popen(
        [sys.executable, SERVIDOR_PATH],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=BASE_DIR,
    )

    # Esperar a que el servidor levante
    time.sleep(3)

    # Verificar si el servidor inicio correctamente
    if servidor.poll() is not None:
        print("  ERROR: El servidor mock no pudo iniciar.")
        print(f"  Salida: {servidor.stdout.read().decode()}")
        sys.exit(1)

    print("  Servidor mock iniciado en http://localhost:3000")

    # 2. Ejecutar demo integrado
    print("\n[2/3] Ejecutando demo integrado...")
    try:
        with open(LOG_PATH, "w", encoding="utf-8") as log_file:
            cliente = subprocess.Popen(
                [sys.executable, CLIENTE_PATH],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=BASE_DIR,
            )
            cliente.wait(timeout=120)
    except subprocess.TimeoutExpired:
        print("  El demo excedio el tiempo maximo. Abortando.")
        cliente.kill()
    finally:
        print("\n[3/3] Deteniendo servidor mock...")
        servidor.send_signal(signal.SIGTERM)
        try:
            servidor.wait(timeout=5)
        except subprocess.TimeoutExpired:
            servidor.kill()

    # 3. Mostrar log
    print("\n" + "=" * 60)
    if os.path.exists(LOG_PATH):
        print(f"  Log guardado en: {LOG_PATH}")
        print("  Ultimas 20 lineas:")
        print("-" * 40)
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines[-20:]:
                print(f"  {line.rstrip()}")
    else:
        print("  No se genero el archivo de log.")

    print("=" * 60)

    # 4. Ejecutar tests de invariantes
    print("\nEjecutando tests de invariantes...")
    test_result = subprocess.run(
        [sys.executable, os.path.join(BASE_DIR, "test_circuit_breaker.py")],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
    )
    print(test_result.stdout)
    if test_result.returncode != 0:
        print("  Tests fallaron!")
        print(test_result.stderr)

    print("\n" + "=" * 60)
    print("  Proceso completado.")
    print("=" * 60)


if __name__ == "__main__":
    main()