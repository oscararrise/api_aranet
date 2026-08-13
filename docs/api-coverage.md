# Cobertura de la API Aranet Cloud

Análisis contrastado con la especificación OpenAPI 3.0.3 publicada por Aranet Cloud. La
API expone 27 operaciones `GET`: el ETL consume las 23 que devuelven JSON y deja fuera
únicamente cuatro descargas binarias. Los campos originales de cada entidad o lectura se
conservan en `raw_payload JSONB`, además de las columnas normalizadas.

| Endpoint | Estrategia | Destino |
|---|---|---|
| `GET /api/v1/bases` | Catálogo y descubrimiento | `base_station`, `tag_assignment` |
| `GET /api/v1/bases/base/{base}` | Detalle por base | `base_station`, `resource_snapshot` |
| `GET /api/v1/sensors` | Catálogo y descubrimiento | `sensor` y relaciones |
| `GET /api/v1/sensors/sensor/{sensor}` | Detalle por sensor | `sensor`, `sensor_probe`, `sensor_capability`, `sensor_base_pairing` |
| `GET /api/v1/sensors/types` | Catálogo | `sensor_type` |
| `GET /api/v1/sensors/types/type/{sensortype}` | Detalle por tipo | `sensor_type`, `resource_snapshot` |
| `GET /api/v1/metrics` | Catálogo | `metric`, `metric_unit` |
| `GET /api/v1/metrics/{metric}` | Detalle por métrica | `metric`, `resource_snapshot` |
| `GET /api/v1/units/unit/{unit}` | Detalle por unidad descubierta | `unit`, `resource_snapshot` |
| `GET /api/v1/assets` | Catálogo y descubrimiento | `asset` y relaciones |
| `GET /api/v1/assets/asset/{asset}` | Detalle por activo | `asset`, `measurement_point`, `measurement_point_capability`, `asset_sensor_association` |
| `GET /api/v1/tags` | Catálogo | `tag`, `tag_assignment` |
| `GET /api/v1/tags/tag/{tag}` | Detalle por tag | `tag`, `resource_snapshot` |
| `GET /api/v1/alarms/rules` | Catálogo | `alarm_rule` |
| `GET /api/v1/alarms/rules/rule/{rule}` | Detalle por regla | `alarm_rule`, `resource_snapshot` |
| `GET /api/v1/alarms/actual` | Cada sincronización | `alarm` con estado activo |
| `GET /api/v1/alarms/history` | Backfill e incremental por ventana | `alarm` |
| `GET /api/v1/measurements/history` | Ventanas, lotes de sensores y paginación completa | `measurement` particionada |
| `GET /api/v1/measurements/last` | Estado más reciente | `measurement` particionada |
| `GET /api/v1/telemetry/history` | Ventanas, lotes de sensores y paginación completa | `telemetry` particionada |
| `GET /api/v1/telemetry/last` | Estado técnico más reciente | `telemetry` particionada |
| `GET .../attachment/{attid}` para sensor | Metadata referenciada por cada sensor | `attachment` |
| `GET .../attachment/{attid}` para activo | Metadata referenciada por cada activo | `attachment` |
| `GET .../attachment/{attid}/file` para sensor | No se descarga: contenido binario | URL y metadata en `attachment` |
| `GET .../attachment/{attid}/thumbnail` para sensor | No se descarga: contenido binario | URL y metadata en `attachment` |
| `GET .../attachment/{attid}/file` para activo | No se descarga: contenido binario | URL y metadata en `attachment` |
| `GET .../attachment/{attid}/thumbnail` para activo | No se descarga: contenido binario | URL y metadata en `attachment` |

## Por qué no se guardan los binarios en PostgreSQL

Las rutas de archivo y miniatura no son JSON y pueden devolver objetos grandes. El ETL
guarda nombre, MIME type, tamaño, fecha y URLs, que sí son información estructurada. Si en
una fase posterior se necesita conservar el contenido, debe copiarse con checksum a S3 o
MinIO y registrar su clave en PostgreSQL. Esto evita inflar backups, WAL y réplicas de la
base transaccional.

## Observaciones verificadas contra la cuenta

- La autenticación se envía en el header `ApiKey`.
- Los IDs llegan como strings, aunque algunos modelos antiguos los describan como enteros.
- Los filtros históricos funcionan con `sensor.id`, no con el código físico `sensorId`.
- La paginación histórica puede llegar en el header `NextLink`; el cliente también soporta
  el campo `next` documentado en el cuerpo.
- Las mediciones pueden estar asociadas directamente a un sensor o a un
  `asset`/`measurement point`; ambas formas tienen claves naturales diferentes.
