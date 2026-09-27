# 📱 Comparador Súper (app móvil)

App para iPhone y Android que busca tu lista de la compra en **Mercadona, Dia,
Consum, Carrefour, Alcampo y Eroski** y te dice dónde es más barato cada
artículo, con filtros de calidad (🌱 eco/bio, 🐔 camperos, 🌾 integral, 🫒
virgen extra, 🍚 bomba, 🏷️ D.O./IGP, sin lactosa, sin gluten) y cesta eco.

El móvil consulta las webs de las tiendas **directamente desde tu conexión**,
así que los precios son los reales del momento. La lista y los ajustes se
guardan en el móvil.

## Instalarla

### Android (gratis, sin tienda)

1. En el móvil, abre la página de **Releases** del repositorio en GitHub
   (`github.com/asierenux/blank-app/releases`) y descarga `comparador-super.apk`
   de la última «App Android».
2. Ábrelo y acepta instalar apps de «orígenes desconocidos» si te lo pide.

El APK se compila solo con GitHub Actions cada vez que cambia la app
(workflow `.github/workflows/android-apk.yml`).

### iPhone

Apple no permite instalar un archivo como en Android. Hay dos opciones:

- **Expo Go (gratis):** instala *Expo Go* desde el App Store. En un ordenador,
  dentro de esta carpeta, ejecuta `npm install` y `npx expo start --tunnel`, y
  escanea el código QR con la cámara del iPhone. La app funciona mientras el
  ordenador tenga ese comando en marcha.
- **App instalada de verdad (TestFlight):** necesita una cuenta de Apple
  Developer (99 $/año). Con ella:
  ```
  npx eas-cli@latest login
  npx eas-cli@latest build --platform ios --profile production
  npx eas-cli@latest submit --platform ios
  ```
  y luego se instala desde la app TestFlight. No hace falta tener Mac.

Expo Go también funciona en Android si prefieres probar sin instalar el APK.

## Desarrollo

```
npm install
npx expo start      # abre la app en Expo Go
npm test            # tests de la lógica (tiendas, calidades, cesta)
npm run typecheck
```

- `src/core/` – lógica sin interfaz: conectores de cada tienda (`stores.ts`),
  calidades (`quality.ts`), comparación y cesta (`compare.ts`), datos demo.
- `src/ui/` – pantallas: Lista, Resultados y Ajustes.
- `App.tsx` – navegación por pestañas y estado.

Las tiendas no tienen APIs oficiales: la app usa las mismas consultas que sus
webs. Si una tienda falla, en *Resultados* aparece el aviso con el error
(tócalo para ver el detalle), y el resto sigue funcionando.

En la versión web (`npx expo start --web`) las tiendas no responden por
restricciones del navegador (CORS); úsala solo con el modo demo.
