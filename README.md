# Asistente Virtual con IA para Telegram

## Descripción

Este bot de Telegram ofrece servicios de inteligencia artificial basados en diferentes modelos predefinidos. Cada usuario recibe 5 créditos permanentes para utilizar el servicio.

## Características

- Múltiples modelos de IA disponibles (General Assistant, Code Assistant, Artist, etc.)
- Cada usuario tiene 5 créditos permanentes
- Interfaz sencilla y fácil de usar
- Respuestas personalizadas según el modelo seleccionado

## Requisitos

- Python 3.7+
- Telegram Bot Token
- OpenAI API Key

## Instalación

1. Clona este repositorio
2. Instala las dependencias:

```bash
pip install -r requirements.txt
```

3. Crea un archivo `.env` con las siguientes variables:

```
TELEGRAM_TOKEN=tu_token_de_telegram
OPENAI_API_KEY=tu_api_key_de_openai
ADMIN_USER_ID=id_del_administrador (opcional)
```

## Uso

Para iniciar el bot, ejecuta:

```bash
python bot.py
```

Una vez que el bot esté en funcionamiento, puedes interactuar con él en Telegram:

- `/start` - Inicia la conversación con el bot
- `/help` - Muestra información de ayuda
- `/creditos` - Consulta tus créditos disponibles
- `/modelos` - Ver los modelos de IA disponibles
- `/modelo [nombre]` - Seleccionar un modelo específico
- Cualquier otro mensaje será procesado por la IA y recibirás una respuesta

## Personalización

Puedes modificar los modelos de IA editando el archivo `modelos` en el directorio principal.