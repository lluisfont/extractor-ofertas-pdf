"""Criterios de extracción: única fuente para el servidor MCP, la consola y los agentes.

Recogen lo aprendido con folletos reales de Carrefour, Eroski y Gadis. Si una cadena nueva trae
un formato distinto, se añade aquí (y en el README) para que todos los modos lo apliquen igual.
"""

FLUJO = """Flujo de trabajo:
1. listar_folletos -> ver los PDF de la carpeta 'entrada' y su progreso.
2. Para cada página pendiente: leer_pagina -> identifica TODAS las ofertas mirando la imagen y
   usando los importes exactos del texto -> guardar_pagina.
3. Si guardar_pagina devuelve avisos, corrige y vuelve a llamar a guardar_pagina con la lista
   COMPLETA de ofertas de la página (sustituye a la anterior).
4. Cuando no queden páginas pendientes: generar_excel.
Los folletos son largos: el progreso queda guardado por página y se puede continuar en un chat
nuevo (listar_folletos indica las páginas pendientes)."""

CRITERIOS = """Criterios de extracción:

QUÉ ES UNA OFERTA
- Una oferta por producto o grupo de productos anunciado con su propio precio o sello de promoción.
- Ofertas sin precio (solo un sello 3x2, «2ª unidad -50 %», «-30 %»...): precio_oferta = null.
- Ofertas de categoría («En TODOS los aceites -20 %», «En los griegos FEIRACO señalizados»):
  producto = esa descripción.
- Variantes con precio distinto (ENTERA / SEMIDESNATADA, tallas, formatos, «También disponible en
  X a N €»): una oferta por variante. Si varios productos comparten un precio grande pero tienen
  formato o precio por kilo distintos, una oferta por producto con ese precio.
- No son ofertas: portadas y cabeceras sin producto, publicidad de la tarjeta o la app, bases
  legales, sorteos, límites de cupón («Importe máximo…»), cuotas de financiación. Si sus importes
  están en la lista P#, van a precios_no_oferta con su motivo.
- Una página sin ofertas se guarda igualmente con ofertas vacías.

CÓMO REPARTIR LOS IMPORTES (todos son NÚMEROS; si un campo no aparece, null; no inventes)
- precio_oferta: el precio grande destacado. nota_precio_oferta: qué significa («€/kg», «La unidad»,
  «Comprando 3, la unidad sale a», «La 2ª unidad sale a», «Llevando 2 la unidad sale a»...).
- precio_normal: el precio anterior tachado, «antes»/«PVP», o el de una unidad («1 unidad 4,89€»,
  «Llevando 1 unidad: 1,99€»).
- precio_total_lote + unidades_lote: el precio del lote («3 unidades 9,78€»; «2 unidades por 3€»
  -> 3 y 2). En «N unidades por X€» deja precio_oferta en null si no hay un precio por unidad
  impreso: el Excel calcula X/N y lo indica.
- precio_segunda_unidad: «la 2ª unidad 0,89 €/ud».
- cupon_euros: cupón o ahorro para la próxima compra («AHORRA 0,58 €» del precio Club).
- descuento_pct: el porcentaje anunciado sin signo (7 para «-7 %», 50 para «2ª unidad -50 %»).
- precio_unitario: precio por kg/l/ud CON la promoción («El kg sale a», «2 uds: 5,37 €/kg»,
  «(3,28€ Kilo)»). precio_unitario_normal: el de sin promoción. Si hay dos por kg, el del
  recuadro de la promoción es precio_unitario. En rangos de peso variable «12,07-12,67 €/kg»:
  el primero en precio_unitario y el segundo en precio_unitario_normal.
- condiciones: tarjeta Club/Oro, «si eres del Club», «COMBINA», «señalizados», máximo de
  unidades, solo hipermercados, puntos extra...
- vigencia: solo si la oferta tiene fechas propias distintas de las del folleto.

LEER LOS IMPORTES
- Usa los importes EXACTOS del texto. En los precios grandes los céntimos y el «€» pueden venir
  separados o apilados («3 ,26 €» = 3,26).
- Páginas de IMAGEN (texto leído por OCR): la imagen manda. Si un P# es una lectura errónea del
  OCR, ponlo en precios_no_oferta con motivo «lectura OCR errónea: en la imagen pone X». Los precios
  enteros dentro de círculos («2€», «3€») el OCR no los lee: pon el importe que ves en la imagen;
  quedan en una lista aparte para una segunda lectura y no hace falta cambiarlos.

AVISOS DE guardar_pagina
- «Precios del PDF que no están en ninguna oferta»: añade la oferta que falta o, si de verdad no es
  una oferta, ponlo en precios_no_oferta con su motivo.
- «Importes que NO aparecen en el texto»: revisa si está mal leído o calculado. Si según la imagen
  es correcto, déjalo y menciónalo al terminar.
- La página está terminada cuando queda VERIFICADA (o VERIFICADA (OCR))."""

INSTRUCCIONES = "Extractor de ofertas de folletos PDF de supermercado a Excel.\n\n" + FLUJO + "\n\n" + CRITERIOS
