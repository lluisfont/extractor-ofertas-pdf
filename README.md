# Extractor de ofertas de folletos PDF

Convierte un folleto PDF de supermercado en un Excel con **todas** sus ofertas, usando
**Claude Desktop** o **ChatGPT Desktop** para interpretar las páginas y el propio PDF para
**verificar** cada precio. No necesita API key: usa la suscripción de tu app de escritorio.

## Cómo funciona

El proyecto es un **servidor MCP**. La app de escritorio lo conecta y su modelo usa estas herramientas:

| Herramienta | Qué hace |
|---|---|
| `listar_folletos` | PDF de `entrada/` y su progreso (páginas pendientes / con avisos). |
| `leer_pagina` | Imagen de la página + capa de texto con coordenadas + lista de precios detectados (P1, P2…). |
| `guardar_pagina` | Recibe las ofertas de la página y **las verifica contra el PDF**. |
| `estado_folleto` | Resumen del progreso. |
| `generar_excel` | Crea el Excel en `salida/` y mueve el PDF a `procesados/`. |

El modelo entiende la maquetación (qué texto va con qué oferta, sellos 3x2 sin precio, «Comprando 3,
la unidad sale a»…). El servidor comprueba lo que devuelve:

- **Nada inventado:** cada importe devuelto debe existir en el texto del PDF.
- **Nada olvidado:** cada precio del PDF debe estar en una oferta o descartado con motivo
  (textos legales, límites de cupón…). Si no, `guardar_pagina` devuelve la lista y el modelo corrige.
- **Progreso guardado por página** (`salida/.sesiones/`): los folletos largos se pueden continuar en
  otro chat.

## Instalación (Windows)

```bash
pip install -r requirements.txt
```

```bash
python instalar_mcp.py
```

El instalador registra el servidor en Claude Desktop y en ChatGPT Desktop (Codex) si los encuentra,
con copia de seguridad de su configuración. Después **cierra la app del todo y ábrela de nuevo**.
Para quitarlo: `python instalar_mcp.py --quitar`.

### Claude Desktop
Se registra en `%APPDATA%\Claude\claude_desktop_config.json`. Aparecerá «extractor-ofertas» en el menú
de conectores del chat.

### ChatGPT Desktop
- **Modo Codex / Work:** ejecutan servidores MCP locales. El instalador lo registra en
  `%USERPROFILE%\.codex\config.toml`.
- **Chat normal:** solo admite servidores MCP remotos. Arranca el servidor por HTTP
  (`python -m extractor_ofertas mcp --http`, puerto 8765) y conéctalo con el *Secure MCP Tunnel* de
  OpenAI en Modo desarrollador.

## Uso

1. Copia el folleto en `entrada/`.
2. En el chat: **«Procesa el folleto de la carpeta entrada con extractor-ofertas»**
   (en Claude Desktop también está el prompt `procesar_folleto`).
3. El modelo recorre las páginas, corrige lo que la verificación le señale y genera el Excel en `salida/`.

Un folleto de 78 páginas consume mucho contexto: si el chat se corta, abre otro y pide
«continúa con el folleto»; retoma en la primera página pendiente.

## El Excel

- **Resumen:** totales, vigencia y **estado de verificación** (verde/amarillo/rojo).
- **Ofertas:** producto, marca, formato, precio oferta y su significado, precio normal, descuento,
  promoción, precio del lote, 2ª unidad, cupón, precio por kg/l (promo y normal), condiciones,
  vigencia y alertas (filas amarillas).
- **Auditoria_paginas:** por página, precios detectados, ofertas y estado (pendientes en rojo).
- **Incidencias:** importes no encontrados en el PDF, precios sin oferta y descartes con su motivo.
- **Texto_bruto:** cada línea del PDF y a qué oferta pertenece su precio.

## Modo sin IA (borrador)

`python -m extractor_ofertas procesar folleto.pdf` o `iniciar_vigilante.bat` generan un Excel por reglas
geométricas, sin modelo. Sirve como borrador rápido, pero falla con maquetaciones complejas.

## Tests

```bash
python -m pytest tests -q
```
