# 🥗 Gestor de Macros

Aplicación en Streamlit para gestionar tus macronutrientes diarios: define objetivos de calorías, proteína, carbohidratos y grasas, guarda tus alimentos habituales y registra lo que comes cada día.

## Funcionalidades

- **📊 Hoy**: resumen del día con barras de progreso frente a tus objetivos y el registro detallado.
- **➕ Registrar**: añade entradas al registro, ya sea desde tu lista de alimentos (indicando gramos) o con una entrada manual rápida.
- **🍎 Alimentos**: biblioteca de alimentos con sus macros por cada 100 g, reutilizable al registrar.
- **📈 Historial**: evolución de calorías y macros a lo largo del tiempo.
- **🎯 Objetivos**: configura tus metas diarias de calorías, proteína, carbohidratos y grasas.

Los datos se guardan en una base de datos SQLite local (`data/macros.db`), que no se sube al repositorio.

### Cómo ejecutarla en tu máquina

1. Instala las dependencias

   ```
   $ pip install -r requirements.txt
   ```

2. Ejecuta la app

   ```
   $ streamlit run streamlit_app.py
   ```
