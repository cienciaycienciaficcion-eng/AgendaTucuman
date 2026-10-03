# Prueba local de Cine

Esta copia usa como base la versión `AgendaTucuman_CLIMA_CABECERA_2026-10-01(3)`.
Se conservaron sus colores y distribución visual y se incorporaron:
- fallback de posters con proxy;
- clasificación, nacionalidad y distribuidora cuando existan en metadata;
- ficha de Cinemacenter e IMDb/tráiler cuando estén disponibles;
- sección Próximos estrenos alimentada por `proximos_estrenos`;
- metadata de cine actualizada.

Para probar:
```bat
npm install
npx expo start --web
```
Luego abrir `http://localhost:8081/cine`.
