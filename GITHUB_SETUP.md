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


## Información cinematográfica (TMDB)

El workflow actualiza automáticamente `datos/agenda_peliculas.json` a partir de las películas que
Cinemacenter publica en `datos/cine_cinemacenter_tucuman.json`.

Para activar el enriquecimiento cinematográfico:

1. Crear una cuenta en TMDB y solicitar un **API Read Access Token**.
2. En GitHub abrir:
   **Settings → Secrets and variables → Actions → New repository secret**
3. Crear el secret:
   - **Name:** `TMDB_API_TOKEN`
   - **Secret:** el API Read Access Token de TMDB.
4. Ejecutar manualmente **Actions → Actualizar datos Agenda Tucumán → Run workflow**.

El proceso obtiene, cuando están disponibles:

- título
- título original
- año
- fecha de estreno
- duración
- géneros
- director
- actores
- sinopsis
- póster
- tráilers de YouTube

La aplicación **no contiene el token de TMDB**. El token se usa únicamente en GitHub Actions y nunca se
envía a la APK.

Si el secret no existe, el workflow conserva la información cinematográfica anterior y continúa con
las demás fuentes.

### Licencia y atribución

TMDB indica que su API es gratuita para usos no comerciales siempre que se atribuya TMDB. Para proyectos
comerciales se requiere una licencia comercial. La aplicación debe incluir la atribución indicada por
TMDB y su logo aprobado. Antes de monetizar la aplicación o convertirla en un proyecto comercial, revisar
las condiciones vigentes de TMDB.

Aviso requerido por TMDB:

> This product uses the TMDB API but is not endorsed or certified by TMDB.

Fuente oficial: https://developer.themoviedb.org/docs/faq
