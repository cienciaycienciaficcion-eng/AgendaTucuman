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

Cada sección tiene un botón **Actualizar**.
