# Modelo PostgreSQL

Todas las entidades se almacenan dentro del esquema `aranet`.

## Catálogos y relaciones

| Tabla | Clave | Propósito |
|---|---|---|
| `base_station` | `id` | Base Aranet PRO, firmware, región y configuración disponible |
| `sensor_type` | `id` | Tipo físico o virtual de sensor |
| `sensor` | `id` | Sensor interno; `sensor_code` es el código mostrado por el dispositivo |
| `sensor_base_pairing` | identidad + clave natural | Historial de emparejamiento y retiro |
| `sensor_probe` | `sensor_id, probe_no` | Sondas numeradas, etiquetas y colores |
| `metric` | `id` | Magnitud medida: temperatura, VWC, RSSI, batería, etc. |
| `unit` | `id` | Unidad de medida y precisión |
| `metric_unit` | `metric_id, unit_id` | Unidades permitidas y predeterminadas |
| `sensor_capability` | `sensor_id, metric_id, probe_no` | Métricas que proporciona cada sensor |
| `asset` | `id` | Activo lógico de Aranet Cloud |
| `measurement_point` | `id` | Punto de medición perteneciente a un activo |
| `asset_sensor_association` | `id` | Sensor colocado o retirado de un punto |
| `measurement_point_capability` | `point_id, metric_id` | Métricas habilitadas en el punto |
| `tag` | `id` | Catálogo de tags |
| `tag_assignment` | `entity_type, entity_id, tag_id` | Asignación genérica a base, sensor o activo |
| `attachment` | `entity_type, entity_id, attachment_id` | Metadata; no contiene el binario |

`sensor.id` y `sensor.sensor_code` no son intercambiables. Las pruebas realizadas contra la
API confirmaron que los filtros históricos esperan el ID interno.

## Series temporales

### `measurement`

Contiene variables físicas, ambientales y agrícolas. Una lectura puede pertenecer
directamente a un sensor o representar la continuidad lógica de un punto de activo.

Clave natural:

```text
subject_type + subject_id + source_sensor_id + metric_id + probe_no + measured_at
```

Incluir `source_sensor_id` evita perder una lectura cuando dos sensores se solapan durante
el reemplazo en un mismo punto.

### `telemetry`

Contiene salud técnica del dispositivo. Clave natural:

```text
sensor_id + metric_id + probe_no + measured_at
```

Ambas tablas se particionan mensualmente por `measured_at`. Los índices B-tree optimizan
sensor/métrica/fecha y BRIN permite recorrer periodos grandes con un índice pequeño.

## Alarmas

| Tabla | Propósito |
|---|---|
| `alarm_rule` | Metadata de reglas expuesta por Aranet |
| `alarm` | Inicio, resolución, severidad, umbral y peor valor observado |

La API pública no entrega toda la configuración interna de cada regla. El modelo conserva
solo lo recibido y el payload crudo; no inventa umbrales que no estén presentes.

## Operación del ETL

| Tabla | Propósito |
|---|---|
| `schema_migration` | Versión y checksum de cada migración |
| `sync_run` | Auditoría, contadores, duración y error de cada comando |
| `sync_state` | Watermark exitoso por endpoint |
| `sync_gap` | Rango que debe reprocesarse después de un fallo |
| `resource_snapshot` | Nueva versión de metadata solo cuando cambia su hash |

## Vistas

- `v_latest_measurements`
- `v_latest_telemetry`
- `v_sensor_status`
- `v_active_alarms`

