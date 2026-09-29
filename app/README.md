# Agenda Tucumán — App

Aplicación Expo/React Native para consultar:

- Agenda de eventos de Tucumán.
- Calendario mensual.
- Cartelera vigente de Cinemacenter Tucumán.
- Radio de Agenda Tucumán.
- Enlaces y servicios.

## Datos dinámicos

La app intenta descargar los JSON publicados por este repositorio:

- `datos/agenda_eventos.json`
- `datos/cine_cinemacenter_tucuman.json`
- `datos/radio_tucuman.json`

Si GitHub no está disponible, utiliza los JSON incluidos dentro de `src/data/` como respaldo.

### Configuración

Editar:

`src/config/remote.ts`

y cambiar:

```ts
https://raw.githubusercontent.com/TU_USUARIO/agenda-tucuman/main/datos
```

por la URL real del repositorio.

## Ejecutar

```bash
npm install
npx expo start -c
```

## Android

```bash
npx expo start --android
```

Para generar una build, usar EAS Build según la configuración de Expo del proyecto.
