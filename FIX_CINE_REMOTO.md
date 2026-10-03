# Fix de actualización remota de Cine

Fecha: 2026-10-01

Se corrigió la obtención de la cartelera de Cinemacenter para evitar que una
falla temporal de `raw.githubusercontent.com` haga que la aplicación quede
silenciosamente con el JSON local de una semana anterior.

## Cambios

- GitHub Raw continúa siendo la fuente principal.
- Se agregó jsDelivr como fuente de respaldo.
- La cartelera remota se considera inválida si su `week_end` ya venció.
  En ese caso se intenta automáticamente jsDelivr.
- Se agregó obtención remota de `cine_metadata.json`, manteniendo los
  metadatos locales como respaldo.
- Se mantiene el parámetro de cache-busting para evitar copias antiguas.
- La pantalla Cine vuelve a comprobar la fuente remota al abrir la app y,
  mientras permanece abierta, al volver a estar activa después de una hora.
- Si ambas fuentes remotas fallan, se conserva el JSON local como último
  respaldo.

No se modificó el diseño de Agenda Tucumán ni la interfaz de Cine.

## Fuentes

Principal:
`https://raw.githubusercontent.com/cienciaycienciaficcion-eng/AgendaTucuman/main/datos/`

Respaldo:
`https://cdn.jsdelivr.net/gh/cienciaycienciaficcion-eng/AgendaTucuman@main/datos/`

La cartelera actual publicada en el repositorio fue verificada por separado
y corresponde a la semana 2026-10-01 a 2026-10-07.
