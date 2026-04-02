# Changelog — BiblioMeta

Formato: [Versionado Semántico](https://semver.org/lang/es/)
MAJOR: cambios incompatibles · MINOR: nuevas funcionalidades · PATCH: correcciones

---

## [1.2.0] — 2026-04

### Correcciones
- **Crítico:** `alma.local_control_number` reemplaza a `alma.identifier` para
  resolver identificadores `bimoBNE` en el SRU de Alma — el índice anterior
  devolvía siempre 0 resultados, dejando sin actualizar todos los libros con
  identificador BNE ya conocido
- Campo `653 $a` (palabras clave libres BNE) ahora se incluye como tags adicionales
- Campo `comments` añadido a `touched_fields` — la sinopsis BNE (`520 $a`)
  ahora aparece en el diálogo de merge de Calibre

### Nuevas funcionalidades
- **Modo `both` paralelo** — cuando el idioma no se puede determinar, BNE y LoC
  se consultan en threads simultáneos; gana el resultado con más metadatos
- **Ranking por riqueza de metadatos** — cuando hay múltiples candidatos se
  prioriza el que tiene más campos rellenos (publisher, tags, serie, sinopsis);
  el título actúa como desempate
- **Wikidata condicional** — solo se consulta cuando el resultado principal
  no tiene tags; evita llamadas innecesarias en registros BNE/LoC completos
- **`maximumRecords` dinámico** — 1 registro para queries por ID o ISBN exacto,
  3 para queries por título+autor
- **Cancelación temprana Google Books** — si BNE devuelve sinopsis desde `520 $a`
  el thread de Google Books se cancela antes de procesar
- **Abort temprano en resultado completo** — si el primer resultado tiene todos
  los campos clave rellenos, no se procesan los siguientes candidatos
- **Timeout dinámico por servidor** — los timeouts se ajustan automáticamente
  durante la sesión según el historial de tiempos de respuesta de cada servidor
- **Validación ISBN** antes de lanzar queries — ISBNs malformados se ignoran
  con aviso en lugar de causar queries fallidas
- **Logging reducido** — solo warnings y errores por defecto; nivel DEBUG
  activable desde la pantalla de configuración para diagnóstico

---

## [1.1.0] — 2026-04

### Correcciones
- `_clean_cdu_code` — limpia anotaciones de localidad BNE dentro de paréntesis
  geográficos: `(460.353 Morón)` → `(460.353)`; cierra paréntesis abiertos sin cerrar
- `_CDU_COUNTRY` — corregido `460.353 = Sevilla` (era incorrecto);
  ampliadas provincias andaluzas, catalanas, gallegas y vascas
- `_CDU_CENTURY` — corregida convención de prefijo de año BNE:
  `"19"` = s.XX (no s.XIX), `"18"` = s.XIX
- Eliminado fallback Open Library por título+autor — devolvía datos de baja
  calidad que ensuciaban la biblioteca; solo se usa Open Library por ISBN exacto
- Fix importación `get_icons` en el plugin de barra de herramientas
- Panel de estado incluye contador de resultados vía Wikidata

### Nuevas funcionalidades
- **Wikidata** como tercer nivel de fallback — para obras clásicas sin ISBN
  aporta género literario, nombre de serie y fecha de publicación original;
  búsqueda por título en el idioma correspondiente
- **`_extract_geo_locality`** — extrae la localidad de anotaciones BNE como
  tag adicional: `94(460.353 Morón)(093)` genera el tag `Morón`
- **Detección de idioma mejorada** — prefijos ISBN iberoamericanos
  (`9788`, `97895`, `9789580`, `9789876`...) identifican español automáticamente;
  `9780`/`9781` identifican inglés; sin datos suficientes prueba ambas cadenas
- Expansión LCC: `PZ3` (Classic Fiction), `PZ4`, `PZ7` (Children's Literature),
  `PZ8` (Folklore) con traducciones específicas
- Expansión CDU acumulada: `087.x`, `316.xxx`, `330.5xx`, `338.1xx`,
  `512.6x`, `616.8xx`, países de África y Oriente Medio

---

## [1.0.0] — 2026-03

Lanzamiento inicial. Renombrado desde **BNE Spain v3.2** con arquitectura
extendida para soporte bilingüe.

### Respecto a BNE Spain v3.2

#### Nuevas funcionalidades
- Soporte bilingüe español/inglés con detección automática de idioma
- Modo de idioma configurable: todos / solo español / solo inglés
- Cadena inglesa: Library of Congress SRU → Open Library → Google Books
- Traductor LCC (Library of Congress Classification) en inglés
- Identificadores directos `bne:` y `loc:` como prioridad máxima — acceso
  directo al registro exacto en sucesivas descargas
- Limpieza de título mejorada: elimina prefijos numéricos (`04 - Título`)
  y paréntesis al inicio y final (`(Serie X) Título`, `Título [2023]`)
- Plugin de barra de herramientas (InterfaceAction) con menú y panel de estado
- Estadísticas de sesión: libros procesados, encontrados, fuente utilizada

#### Cambios de BNE Spain
- Nombre: `BNE Spain` → `BiblioMeta`
- Autor: `Claudio` → `Ludovico`
- Clase Python: `BNESpain` → `BiblioMeta`
- Archivo de importación: `plugin-import-name-bne.txt` → `plugin-import-name-bibliometa.txt`
- Configuración: `BNESpain.json` → `BiblioMeta.json`
- Versión reiniciada en `1.0.0`

---

## Historial BNE Spain (predecesor)

### [3.2.0]
- Paralelismo BNE + Google Books en threads simultáneos
- `maximumRecords=1` con ISBN para reducir payload
- Eliminado `sleep(0.1)` — backoff exponencial ante 429
- Timeouts diferenciados: BNE 20s / Google Books 8s / Open Library 10s
- `_CDU_CENTURY` corregido (convención prefijo de año BNE)
- Auxiliares étnicos CDU `(=XXX)` implementados
- Historia + país: `94(520)` → `Historia de Japón` (sobreescribe región implícita)
- Auxiliares de forma CDU `(0...)` descartados correctamente
- `_clean_cdu_code` — limpieza de anotaciones de sujeto en campo 080
- `_extract_bio_subject` — sujeto biográfico como tag adicional
- Detección de idioma en comments de Google Books (descarta neerlandés, alemán, etc.)
- `_extract_surname` — ignora apellidos < 3 chars, split por `;` y `&`
- Fallback Open Library por título+autor cuando no hay ISBN
- Expansión CDU: `087.x`, `316.xxx`, `330.5xx`, `338.1xx`, `512.6x`, `616.8xx`,
  provincias españolas, países de África y Oriente Medio

### [3.1.0]
- Google Books llamado una sola vez por ISBN (no N veces por resultado del lote)
- Filtro de traducciones: `alma.lang="spa"` en queries por título
- Safety net client-side por `041 $a` para ediciones no españolas
- Uso de `240 $a` (título uniforme) cuando la edición no es en español
- Open Library como segundo nivel de fallback de metadatos
- Ranking por similitud de título para desambiguar series con mismo ISBN
- Pantalla de configuración: fuentes activas, CDU, género/forma, reemplazar tags
- Opción "Reemplazar tags": cuando activa, `tags` entra en `touched_fields`

### [3.0.0]
- Arquitectura v3: BNE primaria + Google Books paralelo + Open Library portadas
- `download_cover()` implementado; capabilities incluye `"cover"`
- Filtro de traducciones por `041 $a` y `alma.lang`
- Traductor CDU completo con formas literarias, países y siglos
- Extracción de serie desde campos `490`, `830`, `440`
- Inversión de autores formato MARC (`Apellido, Nombre` → `Nombre Apellido`)
