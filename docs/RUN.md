# Ejecutar AERVIGIA v0.2 — laboratorio local

**Alcance:** simulación, almacenamiento local opcional y revisión humana. No se conecta a ningún sensor real. **No desplegar públicamente**.

## Opción recomendada: Docker Compose

```bash
docker compose up --build
```

Abre http://127.0.0.1:8000.

- Simulador en marcha: dos fuentes y coordenadas ficticias cada 1,5 s.
- Persistencia SQLite habilitada en el volumen Docker nombrado `aervigia-data`.
- Retención: 7 días por defecto, aplicada al **arranque** (aún no se aplica continuamente en segundo plano).
- Puerto publicado solo en `127.0.0.1` del anfitrión.
- Acceso de lectura local abierto si no estableces `AERVIGIA_VIEW_TOKEN`.
- Los cambios están deshabilitados a menos que definas `AERVIGIA_API_TOKEN`.

Para probar los roles de consulta y operador (valores de ejemplo; genera los tuyos):

```bash
export AERVIGIA_VIEW_TOKEN="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
export AERVIGIA_API_TOKEN="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
export AERVIGIA_OPERATOR_ID="operador-demo"
docker compose up --build
```

En el panel, introduce la clave de consulta en el campo correspondiente.
La clave de operador sirve para reconocer alertas. No se guarda ninguna clave en `localStorage` ni en el repositorio. No comparta claves entre operadores reales: aún no existe autenticación nominal.

> Nota: los operadores comparten una única credencial en esta versión. El campo `AERVIGIA_OPERATOR_ID` etiqueta acciones con un nombre **configurado**, no demuestra la identidad personal de quien las realizó. RBAC individual y auditoría resistente a manipulaciones quedan pendientes.

## Python (sin Docker)

Requisitos: Python 3.12+.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
mkdir -p data
export AERVIGIA_DB_PATH="$PWD/data/aervigia.sqlite3"
export AERVIGIA_RETENTION_DAYS="7"
uvicorn aervigia.app:app --host 127.0.0.1 --port 8000
```

Sin `AERVIGIA_DB_PATH`, la aplicación sigue funcionando íntegramente en memoria, como v0.1. El directorio `data/` está excluido de Git. La variable `AERVIGIA_RETENTION_DAYS` acepta valores enteros entre 1 y 30.

## API local

| Método | Ruta | Acceso | Función |
| --- | --- | --- | --- |
| GET | /healthz | Anónimo | Salud del prototipo |
| GET | /api/state | Clave de consulta si se configura | Estado ficticio actual |
| GET | /api/audit | Clave de consulta si se configura | Últimas revisiones/reinicios |
| POST | /api/observations | X-API-Key | Ingresar observaciones **solo simuladas** |
| POST | /api/alerts/{id}/ack | X-API-Key | Revisar una alerta |
| POST | /api/simulation/reset | X-API-Key | Reiniciar estado actual y registrar el reinicio |

Encabezado de consulta: `X-View-Key: <clave>`. Un operador con `X-API-Key` también puede leer. Si `AERVIGIA_VIEW_TOKEN` no está configurado, la lectura funciona sin credenciales solo en el laboratorio local.

**Persistencia tras reinicio:** se reconstruyen las trayectorias, alertas y acciones a partir del diario SQLite. El simulador reanuda una nueva secuencia ficticia con identificadores de eventos únicos, sin sensores reales.

## Seguridad y límites conocidos

- SQLite es un diario de eventos local y **no** un registro inmutable ni certificado.
- Las claves de roles son compartidas, no hay cuentas de usuarios ni sesiones individuales.
- El borrado automático de registros antiguos ocurre al **iniciar**, no de forma continua. Cualquier política estricta de retención necesita ampliar este módulo y validar la eliminación de copias de seguridad.
- No hay cifrado en reposo, límite de peticiones ni una configuración de seguridad para Internet. No expongas el panel/API a la red.
- Las trayectorias corresponden a una fuente de simulación por pista, no a correlación/fusión multisensor real.
- No hay RF, radar, Remote ID, EO/IR, neutralización, orientación de armas ni actuaciones autónomas.
