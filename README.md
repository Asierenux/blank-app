# Dibujador de Perfiles

App de escritorio para **Windows** que dibuja un perfil/sección a partir de las medidas de una
**consigna de calidad** (Excel o CSV), con sus cotas, tolerancias y el estado **OK / NOK** de cada
medida.

> 🔒 **Funciona sin conexión.** La app no se conecta a internet: tus consignas y medidas no salen
> de tu equipo.

![Ejemplo](ejemplos/captura_tubo.png)

## Cómo conseguir el .exe

**Opción A – descargarlo ya compilado (GitHub Actions)**
Cada vez que se sube código, GitHub compila el ejecutable en una máquina Windows.
Ve a la pestaña **Actions** del repositorio → la última ejecución de *Compilar .exe para Windows* →
descarga el artefacto **DibujadorPerfiles-windows** (zip con el `.exe`, los ejemplos y este README).
Descomprime y haz doble clic en `DibujadorPerfiles.exe`. No hace falta instalar nada.

**Opción B – compilarlo en tu PC**
Con Python 3.11+ instalado, doble clic en `build_exe.bat`. El ejecutable queda en `dist\`.

Para usarlo sin compilar: `pip install -r requirements.txt` y `python app.py`.

## Formato de la consigna

Un Excel con dos hojas, **Perfil** y **Cotas** (mira `ejemplos/perfil_tubo.xlsx`, o usa el botón
*Guardar plantilla de ejemplo* dentro de la app).
En CSV: `nombre_perfil.csv` + `nombre_cotas.csv` en la misma carpeta (separador `;` o `,`,
decimales con coma o punto).

### Hoja «Perfil» — un punto por fila, en orden

| Columna   | Qué es |
|-----------|--------|
| Contorno  | Nombre del contorno (`Exterior`, `Interior`…). Un contorno dentro de otro se dibuja como hueco. |
| Punto     | Nombre del punto (`E1`, `A`…). Se usa en las cotas. |
| X, Y      | Coordenadas en mm. |
| Longitud, Angulo | Alternativa a X/Y: tramo desde el punto anterior (ángulo en grados, 0 = derecha, 90 = arriba). |
| Radio     | Redondeo de la esquina en ese punto (opcional). |
| Tipo      | `P` punto (por defecto) · `C` círculo/taladro (X, Y = centro, con `Diametro`). |
| Cerrado   | `NO` para un perfil abierto (por defecto se cierra). |

### Hoja «Cotas» — una cota de la consigna por fila

| Columna   | Qué es |
|-----------|--------|
| Nombre    | Descripción de la cota. |
| Tipo      | `H` horizontal · `V` vertical · `L` alineada · `D` diámetro · `R` radio. |
| Desde, Hasta | Puntos entre los que se mide (`D` y `R` solo usan *Desde*). |
| Nominal   | Valor nominal (si se deja vacío, se calcula del dibujo). |
| Tol+, Tol- | Tolerancias (o una única columna `Tol` para ±). |
| Medido    | Opcional: valor real medido → la app lo marca **OK** (verde) o **NOK** (rojo). |
| Offset    | Opcional: distancia de la línea de cota al perfil; negativo = al otro lado. |

Si las coordenadas del perfil no cumplen la cota nominal de la consigna, la cota sale en **ámbar**
y la app muestra un aviso.

## Exportar

PDF, PNG (300 ppp), SVG o **DXF** (abre en AutoCAD/LibreCAD con capas PERFIL, EJES y COTAS).

## Desarrollo

```
pip install -r requirements-build.txt
python -m pytest
```
