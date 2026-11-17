# AERVIGIA v0.3.0 — Laboratorio local de observaciones simuladas

**No apto para despliegue público ni decisiones operativas.** Las trayectorias, zonas y eventos son ficticios; ningún sensor real está conectado.

## Arranque sencillo (modo de compatibilidad)

```bash
docker compose up --build
```

Abre http://127.0.0.1:8000. El panel es de solo lectura hasta configurar una clave de escritura; por defecto Docker solo publica el puerto en `127.0.0.1`.

La demo v0.3.0 mantiene el antiguo modo local de claves compartidas mientras no se configure `AERVIGIA_USERS_FILE`. **Para pruebas con varios operadores se recomienda el modo de cuentas individuales siguiente.**

## Cuentas individuales y roles — modo recomendado

La identidad se valida mediante un token personal aleatorio, almacenando en disco únicamente su hash SHA-256. Cada petición revalida el registro para que **revocar una cuenta sea efectivo sin reiniciar**.

Roles:
- `viewer`: consultar estado y auditoría.
- `operator`: consultar, cargar eventos **sintéticos**, revisar y cerrar incidentes.
- `admin`: también reiniciar la simulación.

Los usuarios se crean dentro del volumen persistente de Docker, sin publicar el fichero ni incluirlo en el repositorio:

```bash
docker compose run --rm aervigia-demo python -m aervigia.auth --file /app/data/users.json add --user adminDemo --role admin
docker compose run --rm aervigia-demo python -m aervigia.auth --file /app/data/users.json add --user operadora01 --role operator
docker compose run --rm aervigia-demo python -m aervigia.auth --file /app/data/users.json add --user lectura01 --role viewer
```

**Guarda cada token que aparezca en un gestor de contraseñas:** se muestra una vez y no se puede recuperar. Los tokens no deben copiarse a Git, incidencias, capturas o documentación pública.

Activa el registro de usuarios:

```bash
export AERVIGIA_USERS_FILE=/app/data/users.json
docker compose up --build
```

En el panel introduce únicamente tu credencial personal; el sistema detecta el modo de acceso automáticamente. El token solo permanece en memoria de la pestaña. En el modo de cuentas individuales, **las antiguas claves compartidas dejan de funcionar**, aunque sigan definidas en el entorno.

Para revocar un operador:

```bash
docker compose exec aervigia-demo python -m aervigia.auth --file /app/data/users.json revoke --user operadora01
```

Para consultar los identificadores y roles (no muestra tokens):

```bash
docker compose exec aervigia-demo python -m aervigia.auth --file /app/data/users.json list
```

Si se configura `AERVIGIA_USERS_FILE` pero no existe el fichero, la API **rechaza el acceso**, nunca vuelve al modo de claves compartidas.

> No es un servicio de identidad listo para producción: no existen aún sesiones limitadas temporalmente, SSO, MFA, limitación de intentos, gestión centralizada de identidades ni controles de seguridad para Internet. Cada token es permanente hasta su revocación. El registro no es inmutable ni a prueba de manipulaciones.

## Gestión de incidentes (v0.3.0)

El panel incorpora filtros **Abiertos, Pendientes, Revisados, Cerrados y Todos**.
El ciclo requiere intervención humana: **pendiente → revisado → cerrado**.

- Un operador identificado revisa un evento antes de poder cerrarlo. Intentar cerrar sin revisión devuelve HTTP 409.
- Las transiciones registran quién las realizó y cuándo; un cierre duplicado es idempotente y no crea otra acción.
- La referencia visible `INC-...` deriva del ID único de la observación simulada: es reproducible y distinta tras reiniciar una simulación.
- El listado del panel **muestra como máximo los 80 incidentes recientes** por limitaciones del laboratorio. No es un archivo completo e ilimitado. El diario local mantiene los eventos dentro de su retención configurada.
- Los incidentes cerrados desaparecen del filtro «Abiertos», pero permanecen consultables en «Cerrados» mientras sigan en la ventana reciente y de retención.
- Las bases SQLite creadas con v0.2 se migran al abrirlas para registrar los nuevos eventos de cierre.

## Retención continua

El historial de eventos SQLite vive en el volumen Docker `aervigia-data` y se reconstruye tras reiniciar.

- `AERVIGIA_RETENTION_DAYS`: entre 1 y 30; valor por defecto 7.
- `AERVIGIA_RETENTION_SWEEP_SECONDS`: entre 60 y 86.400; valor por defecto 3.600 (1 hora).
- La aplicación purga al arrancar **y periódicamente durante su ejecución**. Después de cada purga reconstruye el estado visible para retirar las observaciones vencidas también de memoria.
- La retención se basa en la hora de ingestión/registro; las observaciones sintéticas pueden tener tiempos propios distintos.
- No hay borrado criptográfico garantizado: SQLite/WAL y copias de seguridad pueden conservar restos. Este mecanismo es apto únicamente para el laboratorio.

## Python sin Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
mkdir -p data
export AERVIGIA_DB_PATH="$PWD/data/aervigia.sqlite3"
python -m aervigia.auth --file "$PWD/data/users.json" add --user adminDemo --role admin
export AERVIGIA_USERS_FILE="$PWD/data/users.json"
uvicorn aervigia.app:app --host 127.0.0.1 --port 8000
```

El directorio `data/` está excluido de Git. Mantén las credenciales y la base de datos fuera del repositorio.

## API

| Método | Ruta | Acceso |
| --- | --- | --- |
| GET | `/healthz` | Salud general, sin datos operativos |
| GET | `/api/auth-mode` | Indica si el modo individual está activado |
| GET | `/api/me` | Identidad y rol de la credencial |
| GET | `/api/state` | Viewer, operator, admin |
| GET | `/api/audit` | Viewer, operator, admin |
| POST | `/api/observations` | Operator, admin; simulaciones únicamente |
| POST | `/api/alerts/{id}/ack` | Operator, admin; marcar como revisado |
| POST | `/api/incidents/{id}/close` | Operator, admin; cerrar solo tras revisión |
| POST | `/api/simulation/reset` | Solo admin |

En modo individual la API admite `Authorization: Bearer <token-personal>`. En modo antiguo, sigue utilizando `X-View-Key` y `X-API-Key` de las variables `AERVIGIA_VIEW_TOKEN` y `AERVIGIA_API_TOKEN`, respectivamente.

**Límites:** no hay observaciones reales, señales RF, radar, Remote ID ni EO/IR. No hay inhibición, neutralización, integración de armas ni decisiones automáticas. No ejecutar con varios procesos de Uvicorn: el diario y el simulador están diseñados para un solo proceso local.

© 2026 Eduardo Yauri. Todos los derechos reservados.
