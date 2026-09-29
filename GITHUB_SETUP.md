# Configuración de GitHub

El repositorio configurado para la app es:

`https://github.com/cienciaycienciaficcion-eng/AgendaTucuman`

## 1. Subir el proyecto

Subí el contenido de este ZIP al repositorio `AgendaTucuman`.

La estructura debe quedar así:

```text
AgendaTucuman/
├── app/
├── extractores/
├── datos/
├── .github/
├── README.md
└── GITHUB_SETUP.md
```

## 2. Configuración de la app

Ya está configurada para consultar:

```text
https://raw.githubusercontent.com/cienciaycienciaficcion-eng/AgendaTucuman/main/datos
```

No hace falta modificar `remote.ts`.

## 3. Probar GitHub Actions

En GitHub:

**Actions → Actualizar datos Agenda Tucumán → Run workflow**

El workflow ejecutará los tres extractores y actualizará:

- `datos/agenda_eventos.json`
- `datos/cine_cinemacenter_tucuman.json`
- `datos/cine_tucuman.json`
- `datos/radio_tucuman.json`

## 4. Funcionamiento

La app intenta obtener los datos actuales desde GitHub.

Si no hay conexión o GitHub no responde, utiliza los datos incluidos dentro de la aplicación como respaldo.

El workflow está programado para ejecutarse cada 6 horas y también puede ejecutarse manualmente.
