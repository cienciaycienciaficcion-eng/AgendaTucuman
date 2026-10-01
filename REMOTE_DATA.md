# Datos remotos

La aplicación consulta automáticamente los datos publicados por GitHub:

- Agenda: `datos/agenda_eventos.json`
- Cine: `datos/cine_cinemacenter_tucuman.json`
- Radio: `datos/radio_tucuman.json`

Repositorio:

`https://github.com/cienciaycienciaficcion-eng/AgendaTucuman`

La app:

1. inicia mostrando los datos incluidos en el APK;
2. intenta actualizar cada fuente desde GitHub;
3. valida el JSON recibido;
4. reemplaza los datos locales en memoria solo si son válidos;
5. si la red falla, continúa usando los datos incluidos.

La Agenda se actualiza automáticamente al abrir la app y vuelve a comprobar el servidor cuando han pasado 8 horas desde la última comprobación; no necesita botón de actualización manual.


### Metadata de películas

El workflow `Actualizar metadata de cine` consulta la cartelera oficial de Cinemacenter cada 6 horas y puede ejecutarse manualmente desde GitHub Actions. Busca las fichas individuales de cada película, extrae poster, sinopsis, estreno, duración, géneros, director, reparto y otros campos disponibles, e inserta esa metadata también dentro de `datos/cine_cinemacenter_tucuman.json`. La app usa primero la metadata publicada junto con la cartelera y conserva la base local como respaldo.
