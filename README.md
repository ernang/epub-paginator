# EPUB 3 Page Break Generator

Un script en Python que añade paginación aproximada compatible con el estándar EPUB 3 a libros electrónicos (EPUB) existentes. 

Ideal para dotar a los EPUBs fluidos (*reflowable*) de números de página de referencia, permitiendo una mejor navegación y manteniendo la compatibilidad con lectores modernos que soportan `page-list`.

> 💡 **Nota importante:** Este proyecto está diseñado y optimizado específicamente para procesar **archivos EPUB resultantes de convertir libros desde formato MOBI mediante Calibre**. El script detecta automáticamente el patrón de nomenclatura y la estructura interna (`index_split_*.html`) que genera Calibre en este tipo de conversiones.

---

## Características

- **Optimizado para Calibre:** Detecta e identifica de forma inteligente la estructura `index_split` generada tras convertir de MOBI a EPUB para iniciar la paginación en el lugar correcto.
- **Paginación automática:** Calcula el número de página insertando saltos basados en la cantidad aproximada de caracteres visibles (por defecto 1500).
- **Compatible con EPUB 3:** Inyecta etiquetas `<span epub:type="pagebreak">` e integra la lista de páginas en el archivo de navegación (`nav.xhtml` mediante `<nav epub:type="page-list">`).
- **Seguro y validado:** No sobreescribe tu archivo original por defecto. Además, valida que el XML siga estando bien formado antes de empaquetar el nuevo EPUB.
- **Soporte CLI y GUI:** Funciona tanto mediante línea de comandos (usando solo la biblioteca estándar de Python) como mediante interfaz gráfica.

---

## Requisitos

- **Python 3.6 o superior**.
- **Librerías estándar:** No se requieren librerías de terceros para la versión de consola.
- *(Opcional)* `customtkinter` si deseas ejecutar o compilar la versión con interfaz gráfica avanzada:
  ```bash
  pip install customtkinter

## Características

- **Paginación automática:** Calcula el número de página insertando saltos basados en la cantidad aproximada de caracteres visibles (por defecto 1500).
- **Compatible con EPUB 3:** Inyecta etiquetas `<span epub:type="pagebreak">` e integra la lista de páginas en el archivo de navegación (`nav.xhtml` mediante `<nav epub:type="page-list">`).
- **Seguro y validado:** No sobreescribe tu archivo original por defecto. Además, valida que el XML siga estando bien formado antes de empaquetar el nuevo EPUB.
- **Sin dependencias externas:** Utiliza exclusivamente la biblioteca estándar de Python 3.

## Requisitos

- **Python 3.6 o superior**.
- No se requiere instalar librerías adicionales mediante `pip`.

## Uso

Ejecuta el script desde tu terminal apuntando al archivo EPUB que deseas modificar:

```bash
python epub_paginador.py "mi_libro.epub"
```

El script generará automáticamente un nuevo archivo llamado `mi_libro - paginado.epub` en el mismo directorio.

### Opciones disponibles

```bash
usage: epub_paginador.py [-h] [--chars CHARS] [--start-file START_FILE] [--output OUTPUT] input

Añade paginación EPUB 3 aproximada a un EPUB.

positional arguments:
  input                 EPUB de entrada

options:
  -h, --help            Muestra este mensaje de ayuda y termina.
  --chars CHARS         Caracteres visibles aproximados por página (por defecto: 1500).
  --start-file START_FILE
                        Archivo HTML/XHTML desde el que comienza la paginación. 
                        Si se omite, intentará detectar el primer archivo de contenido 
                        (ej: `index_split_000.html`).
  --output OUTPUT       Ruta y nombre del EPUB de salida.
```

## Ejemplos

**1. Ajustar el tamaño de la página (ej. 2000 caracteres por página):**
```bash
python epub_paginador.py "libro.epub" --chars 2000
```

**2. Especificar un archivo de salida personalizado:**
```bash
python epub_paginador.py "libro.epub" --output "libro_final.epub"
```

**3. Empezar a contar páginas desde un capítulo específico:**
```bash
python epub_paginador.py "libro.epub" --start-file "capitulo_01.xhtml"
```

## ¿Cómo funciona internamente?

1. **Descompresión:** Lee el EPUB origen y carga su contenido en memoria.
2. **Análisis:** Busca los archivos HTML/XHTML que forman el contenido real del libro, ignorando el índice (TOC) y los menús de navegación.
3. **Inyección:** Recorre los párrafos (`<p>`) contando los caracteres puramente visibles (sin etiquetas HTML). Cuando la suma alcanza el límite (`--chars`), inserta un marcador de salto de página EPUB 3.
4. **Actualización de Metadatos:** Sobreescribe el `nav.xhtml` añadiendo el bloque `<nav epub:type="page-list">` para que los e-readers puedan renderizar la navegación por páginas. Actualiza la fecha de modificación (`dcterms:modified`) en el `content.opf`.
5. **Empaquetado:** Genera un EPUB válido respetando que el archivo `mimetype` no vaya comprimido y sea el primer elemento del ZIP.
