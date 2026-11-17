# Ejecutar AERVIGIA v0.1 — laboratorio local

**Estado:** prototipo de observaciones simuladas. No procesa señales de sensores reales.

## Python (desarrollo)

Requisitos: Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
uvicorn aervigia.app:app --host 127.0.0.1 --port 8000
```

Visita http://127.0.0.1:8000 para ver el panel; http://127.0.0.1:8000/docs para la API.

El simulador empieza automáticamente con dos fuentes ficticias (alpha y bravo) y genera observaciones cada 1,5 segundos. La zona y el mapa son completamente sintéticos.

## Docker

```bash
docker compose up --build
```

El puerto de Docker se publica exclusivamente en 127.0.0.1 de la máquina anfitriona.

## Activar escritura (solo entorno local)

Por defecto las rutas POST están **deshabilitadas**. Para permitir inyección de observaciones sintéticas, reconocimiento de alertas o reinicio:

```bash
export AERVIGIA_API_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')"
uvicorn aervigia.app:app --host 127.0.0.1 --port 8000
```

En el panel, introduce la misma clave en «Clave local de escritura» para reconocer incidentes. La interfaz no almacena ese secreto en disco. Para Docker, establece la variable antes de iniciar Compose.

## API

| Método | Ruta | Acceso | Función |
| --- | --- | --- | --- |
| GET | /healthz | Lectura | Salud del servicio |
| GET | /api/state | Lectura | Estado de simulación, trazas y alertas |
| POST | /api/observations | X-API-Key | Validar e incorporar un evento sintético |
| POST | /api/alerts/{id}/ack | X-API-Key | Reconocer una alerta |
| POST | /api/simulation/reset | X-API-Key | Reiniciar estado en memoria |

Los POST requieren un valor de cabecera X-API-Key igual a AERVIGIA_API_TOKEN. Sin configuración, responderán 503.

## Límites del MVP

- Fuente de cada trayectoria: **un identificador de simulador**, no una fusión multisensor.
- Almacenamiento: solo memoria; se pierde al reiniciar. No hay base de datos ni retención persistente.
- Seguridad: API de escritura con clave; las rutas de lectura son locales, sin autenticación. **No exponer a Internet**.
- Detección real: inexistente. No se han conectado radares, RF, Remote ID ni EO/IR.
- Geometría: zona de demostración y coordenadas ficticias sin validez de navegación.
- Uso: únicamente prototipado y evaluación de experiencia de operador.

## Próximo corte

Persistencia auditable, usuarios y RBAC, geofencing configurable y conectores de fuentes autorizadas tras revisión legal y de seguridad. No se incluyen mecanismos de interferencia ni acciones autónomas.
