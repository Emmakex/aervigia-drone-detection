# AERVIGIA v0.5.2 — Laboratorio local de observaciones simuladas

**No apto para despliegue público ni decisiones operativas.** Las trayectorias, zonas y eventos son ficticios; ningún sensor real está conectado.

## Arranque sencillo (modo de compatibilidad)

```bash
docker compose up --build
```

Abre http://127.0.0.1:8000. El panel es de solo lectura hasta configurar una clave de escritura; por defecto Docker solo publica el puerto en `127.0.0.1`.

La demo v0.5.2 mantiene el antiguo modo local de claves compartidas mientras no se configure `AERVIGIA_USERS_FILE`. **Para pruebas con varios operadores se recomienda el modo de cuentas individuales siguiente.**

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

## Gestión de incidentes (v0.5.2)

El panel incorpora filtros **Abiertos, Pendientes, Revisados, Cerrados y Todos**.
El ciclo requiere intervención humana: **pendiente → revisado → cerrado**.

- Un operador identificado revisa un evento antes de poder cerrarlo. Intentar cerrar sin revisión devuelve HTTP 409.
- Las transiciones registran quién las realizó y cuándo; un cierre duplicado es idempotente y no crea otra acción.
- La referencia visible `INC-...` deriva del ID único de la observación simulada: es reproducible y distinta tras reiniciar una simulación.
- **Protección contra acciones obsoletas:** las API `POST /api/alerts/{id}/ack` y `POST /api/incidents/{id}/close` requieren un cuerpo JSON `{"expected_reference":"INC-XXXXXXXXXXXX"}` con la referencia exacta devuelta en `GET /api/state`. La ausencia del campo devuelve **422**, y una referencia distinta para el ID interno devuelve **409 sin modificar el nuevo incidente ni añadir un evento al diario**. Esta comprobación es necesaria porque el ID interno `SIM-ALERT-0001` puede repetirse al reiniciar un ensayo.
- La interfaz envía la referencia automáticamente y recarga el estado después de un conflicto. Los clientes API anteriores deben actualizarse para incluir ese campo.
- El listado del panel **muestra como máximo los 80 incidentes recientes** por limitaciones del laboratorio. No es un archivo completo e ilimitado. El diario local mantiene los eventos dentro de su retención configurada.
- Los incidentes cerrados desaparecen del filtro «Abiertos», pero permanecen consultables en «Cerrados» mientras sigan en la ventana reciente y de retención.
- Las bases SQLite creadas con v0.2 se migran al abrirlas para registrar los nuevos eventos de cierre.

## Escenarios ficticios (v0.5.2)

El panel incluye el laboratorio de escenarios con **tres presets**:

- **Recorrido estándar** (`standard`): dos pistas sintéticas, una puede entrar en la zona.
- **Sin entradas** (`clear`): dos pistas ficticias que siempre permanecen fuera de la zona.
- **Entradas múltiples** (`dual-entry`): tres pistas ficticias, dos atraviesan la zona y generan alertas separadas.

El catálogo se consulta desde el servidor, no se editan coordenadas reales ni se conecta hardware. Los botones para **Iniciar**, **Pausar** y **Reanudar** solo se habilitan a administradores autenticados. Los roles viewer y operator pueden ver el estado, pero no cambiarlo.

**Iniciar un escenario reinicia el estado visible** (pistas, alertas e incidentes de la sesión actual). Con SQLite, la selección de escenario se registra como evento de reinicio con el identificador y usuario responsable. Los eventos anteriores siguen sujetos a la retención configurada, pero no se mezclan con el estado visible del nuevo ensayo. La pausa/reanudación funciona **solo en memoria**: se pierde al reiniciar el servicio y no constituye auditoría persistente.

Rutas locales:

| Método | Ruta | Acceso |
| --- | --- | --- |
| GET | `/api/simulation/scenarios` | Viewer, operator, admin |
| POST | `/api/simulation/scenarios/{id}/start` | Solo admin |
| POST | `/api/simulation/pause` | Solo admin |
| POST | `/api/simulation/resume` | Solo admin |

**Cambio seguro de escenarios:** el botón «Iniciar escenario» muestra primero un aviso con los efectos de reiniciar y exige confirmar o cancelar. La confirmación envía el `run_id` observado al servidor y este comprueba bajo bloqueo que sigue siendo el ensayo activo. Si otro administrador lo cambió entre tanto, responde **409** sin modificar el historial ni el ensayo actual.

La API `POST /api/simulation/scenarios/{id}/start` requiere JSON `{"expected_run_id":"<run_id-vigente>"}`. Obtén `run_id` de `GET /api/state` con la credencial correspondiente. No reutilices identificadores de una sesión anterior. El endpoint heredado `POST /api/simulation/reset` continúa por compatibilidad, restringido a administradores; no participa en la confirmación del panel.

La simulación sigue siendo **no operativa**: planos abstractos, trayectorias deterministas y eventos imaginarios; no es un sistema certificado para seguridad aérea.

## Informes y exportación (v0.5.2)

El centro de mando permite descargar un informe individual **JSON** por incidente
a usuarios autorizados y exportar un lote reciente como **JSON o CSV** únicamente
a operadores y administradores. El filtro del panel (Abiertos, Pendientes,
Revisados, Cerrados, Todos) también se aplica a las descargas masivas.

- Máximo **80 incidentes recientes del estado actual** por descarga; no es una copia completa del diario ni una exportación histórica entre reinicios.
- Cada informe incluye referencia, estado, tipo, zona de demostración,
  pista simulada, fecha de detección, revisor, fecha de revisión,
  cierre, responsable y marca explícita `simulation: true`.
- **No** incluye coordenadas geográficas, posiciones, señales brutas,
  datos de sensores físicos ni credenciales.
- Las descargas no cambian el estado de un incidente. Los CSV incluyen BOM
  UTF-8 para compatibilidad con hojas de cálculo y neutralizan texto que
  podría ejecutarse como fórmula.
- Los informes son artefactos de demostración y **no** tienen validez
  probatoria, cadena de custodia o firma digital.
- La disponibilidad de incidentes depende de los 80 últimos eventos de la
  simulación y de la retención SQLite. Los registros antiguos y de un
  reinicio anterior no se incluyen en estos archivos.

**Ejemplo local, con cuenta individual de operador (sin exponer el token):**

```bash
curl -fsS -H "Authorization: Bearer ${AERVIGIA_PERSONAL_TOKEN}" \
  "http://127.0.0.1:8000/api/reports/incidents/export?format=csv&status=closed" \
  -o incidentes-simulados.csv
```

Nunca incluyas tokens en el repositorio, en capturas ni en incidencias.

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
| GET | `/api/reports/incidents/{reference}` | Viewer, operator, admin; single simulated report |
| GET | `/api/reports/incidents/export?format=json&status=all` | Operator, admin; bulk JSON/CSV download |
| POST | `/api/observations` | Operator, admin; simulaciones únicamente |
| POST | `/api/alerts/{id}/ack` | Operator, admin; marcar como revisado |
| POST | `/api/incidents/{id}/close` | Operator, admin; cerrar solo tras revisión |
| POST | `/api/simulation/reset` | Solo admin |

En modo individual la API admite `Authorization: Bearer <token-personal>`. En modo antiguo, sigue utilizando `X-View-Key` y `X-API-Key` de las variables `AERVIGIA_VIEW_TOKEN` y `AERVIGIA_API_TOKEN`, respectivamente.

**Límites:** no hay observaciones reales, señales RF, radar, Remote ID ni EO/IR. No hay inhibición, neutralización, integración de armas ni decisiones automáticas. No ejecutar con varios procesos de Uvicorn: el diario y el simulador están diseñados para un solo proceso local.

© 2026 Eduardo Yauri. Todos los derechos reservados.
