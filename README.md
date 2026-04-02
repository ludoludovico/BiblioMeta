# BiblioMeta

**Plugin de metadatos para Calibre — Fuentes autoritativas multiidioma**

BiblioMeta es un plugin de descarga de metadatos para [Calibre](https://calibre-ebook.com) que obtiene información bibliográfica de alta calidad desde fuentes autoritativas para bibliotecas en **español** e **inglés**.

---

## Fuentes

| Fuente | Idioma | Tipo | Datos |
|---|---|---|---|
| **Biblioteca Nacional de España (BNE)** | Español | SRU/MARC21 | Primaria — metadatos completos + CDU |
| **Library of Congress (LoC)** | Inglés | SRU/MARC21 | Primaria — metadatos completos + LCC |
| **Wikidata** | Ambos | SPARQL | Fallback — género, serie, fecha original |
| **Open Library** | Ambos | REST/JSON | Fallback — metadatos básicos por ISBN |
| **Google Books** | Ambos | REST/JSON | Sinopsis y portadas |

Todas las fuentes son **gratuitas y sin API key**.

---

## Características

- **Bilingüe** — detección automática de idioma por prefijo ISBN o identificador; modos forzados español/inglés disponibles
- **Clasificación bibliográfica** — tags CDU traducidos al español (libros españoles) y LCC en inglés (libros anglosajones)
- **Identificadores directos** — reutiliza `bne:` y `loc:` de descargas anteriores para acceso directo al registro exacto sin búsqueda
- **Optimizado para bibliotecas grandes** — paralelismo BNE+Google Books, timeouts dinámicos, abort temprano en resultados completos
- **Pantalla de configuración** — modo de idioma, fuentes activas, comportamiento de tags, modo debug
- **Panel de estado** — estadísticas de sesión con contador por fuente (requiere plugin de barra de herramientas)

---

## Instalación

### Requisitos
- Calibre 5.0.0 o superior
- Python 3.x (incluido en Calibre)

### Pasos

1. Descargar `BiblioMeta.zip` desde la sección [Releases](../../releases)
2. En Calibre: **Preferencias → Plugins → Cargar plugin desde archivo**
3. Seleccionar `BiblioMeta.zip`
4. Reiniciar Calibre

**Opcional — botón en barra de herramientas:**

1. Descargar también `BiblioMetaAction.zip`
2. Instalar del mismo modo
3. Ir a **Preferencias → Barras de herramientas y menús**
4. Arrastrar `BiblioMeta` desde la lista de acciones disponibles a la barra

---

## Configuración

Acceder desde **Preferencias → Plugins → Fuentes de metadatos → BiblioMeta → Personalizar**.

### Modo de idioma

| Opción | Comportamiento |
|---|---|
| **Todos los idiomas** (por defecto) | Detección automática por prefijo ISBN o identificador existente |
| **Solo español** | Usa únicamente la cadena BNE → Open Library → Google Books |
| **Solo inglés** | Usa únicamente la cadena LoC → Open Library → Google Books |

> **Consejo:** Para descargas masivas de una biblioteca en un solo idioma, forzar el modo correspondiente mejora significativamente la velocidad.

### Fuentes

- **Open Library** — fallback por ISBN cuando BNE/LoC no encuentra el libro
- **Wikidata** — fallback para obras clásicas sin ISBN; aporta género literario, serie y fecha de publicación original
- **Google Books** — sinopsis y portadas

### Etiquetas (tags)

- **Reemplazar tags existentes** — cuando está activo, los tags de la fuente primaria sobreescriben los existentes en el diálogo de merge de Calibre
- **Tags CDU** — clasificación española con código y descripción traducida (ej. `CDU:821.134.2-31"19"` + `Literatura española · Novela · s.XX`)
- **Tags LCC** — clasificación Library of Congress con código y descripción en inglés (ej. `LCC:PQ6638.A73` + `Spanish Literature`)
- **Género / forma** — campo 655 de la fuente primaria

---

## Campos descargados

| Campo Calibre | Fuente |
|---|---|
| Título | BNE / LoC / Open Library / Wikidata |
| Autores | BNE / LoC / Open Library / Wikidata |
| Editorial | BNE / LoC / Open Library |
| Fecha publicación | BNE / LoC / Open Library / Wikidata |
| ISBN | BNE / LoC / Open Library |
| Idioma | BNE / LoC |
| Serie y número | BNE / LoC / Wikidata |
| Tags / Clasificación | BNE (CDU) / LoC (LCC) / Wikidata (género) |
| Sinopsis | BNE (520$a) / Google Books |
| Portada | Google Books / Open Library |
| Identificador `bne:` | BNE |
| Identificador `loc:` | LoC |

---

## Cobertura estimada

| Tipo de biblioteca | Cobertura esperada |
|---|---|
| Libros en español con ISBN español (978-84) | 80-90% |
| Libros latinoamericanos (978-95x, 978-98x) | 60-70% |
| Libros en inglés con ISBN anglosajón (978-0, 978-1) | 70-80% |
| Libros de dominio público sin ISBN | 20-40% (vía Wikidata) |

---

## Clasificación CDU

BiblioMeta incluye un traductor CDU que convierte los códigos de la BNE en etiquetas descriptivas en español. Ejemplos:

| Código BNE | Tags generados |
|---|---|
| `821.134.2-31"19"` | `CDU:821.134.2-31"19"` · `Literatura española · Novela · s.XX` |
| `94(460)` | `CDU:94(460)` · `Historia de España` |
| `821.111(73)-32"19"` | `CDU:821.111(73)-32"19"` · `Literatura inglesa · Cuentos y relatos · Estados Unidos · s.XX` |
| `929 García Lorca, Federico` | `CDU:929` · `Biografías y genealogías` · `García Lorca, Federico` |

---

## Limitaciones conocidas

- **Sinopsis:** La cobertura de sinopsis en español es limitada. Se recomienda usar el [plugin Goodreads de kiwidude68](https://github.com/kiwidude68/calibre_plugins) configurado solo para el campo `comments` como complemento.
- **Libros latinoamericanos:** La BNE no tiene depósito legal de ediciones publicadas fuera de España. Open Library cubre parcialmente este segmento.
- **Libros de Gutenberg:** Títulos de dominio público sin ISBN raramente tienen cobertura en LoC vía SRU. Wikidata cubre los clásicos más conocidos.
- **LoC SRU:** El servidor puede devolver errores 502/503 ocasionales tras la migración Voyager→Folio de julio 2025. BiblioMeta implementa retry automático con backoff.
- **Manga:** La BNE cataloga algunos mangas bajo `821.521` (Literatura china) en lugar de `821.521.1` (Literatura japonesa). Es una limitación de la catalogación de la fuente, no del plugin.

---

## Licencia

GPL v3 — ver [LICENSE](LICENSE)

Los datos bibliográficos de la BNE se publican bajo licencia **CC0**.

---

## Créditos

Desarrollado por **Ludovico**.

Fuentes de datos:
- [Biblioteca Nacional de España](https://www.bne.es) — servicio SRU
- [Library of Congress](https://www.loc.gov) — servicio SRU/Z39.50
- [Wikidata](https://www.wikidata.org) — SPARQL endpoint público
- [Open Library](https://openlibrary.org) — API pública
- [Google Books](https://books.google.com) — API pública
