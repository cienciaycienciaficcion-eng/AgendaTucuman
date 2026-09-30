# Agenda Tucumán

Repositorio completo del proyecto **Agenda Tucumán**.

## Arquitectura

```text
agenda-tucuman/
├── app/                         # App Expo / React Native
├── extractores/                # Fuentes Python
│   ├── agenda_mec.py           # Agenda de eventos vía MEC
│   ├── contenidos.py            # Radio + contenidos auxiliares
│   ├── cinemacenter.py         # Cartelera oficial Cinemacenter
│   └── requirements.txt
├── datos/                      # JSON públicos consumidos por la app
└── .github/workflows/
    └── actualizar_datos.yml    # Actualización automática
```

## Fuentes

### Agenda
`agenda_mec.py` consulta Agenda Tucumán mediante MEC/AJAX y WordPress REST. Conserva la lógica del extractor V11.1 proporcionado para el proyecto.

### Cine
`cinemacenter.py` consulta directamente Cinemacenter Tucumán, usando el PDF oficial de horarios (`cityId=13`) y la página oficial de estrenos.

### Radio
`contenidos.py` consulta Agenda Tucumán y el reproductor Shock Media/SonicPanel para detectar la transmisión real. El extractor no inventa una URL de streaming si no encuentra una fuente válida.

## Actualización automática

GitHub Actions ejecuta los tres extractores cada 6 horas y también permite ejecución manual mediante `workflow_dispatch`.

Los archivos seleccionados se publican en `datos/` y la app los consume mediante `raw.githubusercontent.com`.

## Primer uso

1. Crear un repositorio GitHub, por ejemplo `agenda-tucuman`.
2. Subir todo el contenido de este repositorio.
3. La app ya está configurada para `cienciaycienciaficcion-eng/AgendaTucuman`.
4. Hacer commit y push.
5. Abrir GitHub → Actions → **Actualizar datos Agenda Tucumán** → **Run workflow** para probarlo manualmente.
6. Verificar que `datos/` se actualice.
7. Ejecutar la app.

## Dependencias de los extractores

```bash
pip install -r extractores/requirements.txt
```

## Ejecutar extractores manualmente

Agenda:

```bash
python extractores/agenda_mec.py --start-year 2026 --start-month 9 --months 12 --out .tmp/agenda
```

Contenidos/radio:

```bash
mkdir -p .tmp/contenidos
cd .tmp/contenidos
python ../../extractores/contenidos.py
```

Cinemacenter:

```bash
mkdir -p .tmp/cinemacenter
cd .tmp/cinemacenter
python ../../extractores/cinemacenter.py
```

## Estado

La app parte de datos de respaldo ya generados. Los datos remotos se actualizan automáticamente cuando el workflow se ejecuta correctamente.


### Películas

`datos/agenda_peliculas.json` contiene el enriquecimiento cinematográfico generado automáticamente desde las películas detectadas por Cinemacenter. La app lo consume desde GitHub Raw.
