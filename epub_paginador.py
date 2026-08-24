#!/usr/bin/env python3
"""
EPUB 3 Page Break Generator
----------------------------
Añade paginación aproximada EPUB 3 a un EPUB existente.

Uso:
    python epub_paginador.py "libro.epub"

Genera:
    "libro - paginado.epub"

Opciones:
    --chars 1500       Caracteres visibles aproximados por página.
    --start-file ...   Archivo HTML desde el que comienza el contenido principal.
                       Por defecto: detecta el primer index_split_*.html y empieza ahí.
    --output ...       Ruta/nombre del EPUB de salida.
"""

from pathlib import Path
import argparse
import html
import re
import zipfile
from datetime import datetime, timezone
import xml.etree.ElementTree as ET


def visible_text_len(fragment: str) -> int:
    """Cuenta aproximadamente los caracteres visibles de un fragmento HTML."""
    text = re.sub(r"<[^>]+>", "", fragment)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return len(text.strip())


def find_html_files(names):
    """Busca los XHTML/HTML que normalmente contienen el texto del libro."""
    candidates = [
        n for n in names
        if (
            n.lower().endswith((".html", ".xhtml"))
            and not n.lower().endswith("nav.xhtml")
            and "toc" not in Path(n).name.lower()
        )
    ]

    # Si el EPUB de Calibre usa index_split_*.html, los ordenamos naturalmente.
    def natural_key(name):
        parts = re.split(r"(\d+)", name)
        return [int(p) if p.isdigit() else p.lower() for p in parts]

    return sorted(candidates, key=natural_key)


def add_pagebreaks(files, html_files, chars_per_page, start_file=None):
    """
    Inserta marcadores EPUB 3:
        <span epub:type="pagebreak" id="page_N" title="N"></span>

    Devuelve la lista de páginas generadas.
    """
    if start_file:
        if start_file not in html_files:
            raise ValueError(
                f"No se encuentra --start-file: {start_file}"
            )
        start_index = html_files.index(start_file)
    else:
        # Preferimos empezar en el primer index_split_* si existe.
        split_files = [
            n for n in html_files
            if Path(n).name.startswith("index_split_")
        ]
        start_index = html_files.index(split_files[0]) if split_files else 0

    page_no = 1
    accumulated = 0
    pages = []

    for name in html_files[start_index:]:
        text = files[name].decode("utf-8")

        # Evitar procesar dos veces un EPUB ya paginado.
        if 'epub:type="pagebreak"' in text:
            continue

        paragraphs = list(re.finditer(
            r"<p\b[^>]*>.*?</p\s*>",
            text,
            flags=re.IGNORECASE | re.DOTALL
        ))

        if not paragraphs:
            continue

        pieces = []
        last = 0

        for match in paragraphs:
            paragraph = match.group(0)
            plen = visible_text_len(paragraph)

            if plen <= 0:
                pieces.append(text[last:match.end()])
                last = match.end()
                continue

            # Primera página o comienzo de una nueva página.
            if accumulated == 0 or accumulated >= chars_per_page:
                if accumulated >= chars_per_page:
                    page_no += 1

                marker_id = f"page_{page_no}"
                marker = (
                    f'<span epub:type="pagebreak" id="{marker_id}" '
                    f'title="{page_no}"></span>'
                )

                pieces.append(text[last:match.start()])
                pieces.append(marker)
                last = match.start()

                pages.append((page_no, name, marker_id))
                accumulated = 0

            pieces.append(text[last:match.end()])
            last = match.end()
            accumulated += plen

        pieces.append(text[last:])
        files[name] = "".join(pieces).encode("utf-8")

    return pages


def update_nav(files, pages):
    """Añade/reemplaza la navegación page-list EPUB 3 en nav.xhtml."""
    if "nav.xhtml" not in files:
        # Buscar por si el EPUB usa otra ruta/nombre.
        nav_name = next(
            (n for n in files if Path(n).name.lower() == "nav.xhtml"),
            None
        )
        if not nav_name:
            raise ValueError("El EPUB no contiene nav.xhtml.")
        nav_name = nav_name
    else:
        nav_name = "nav.xhtml"

    nav = files[nav_name].decode("utf-8")

    # Eliminar una page-list anterior.
    nav = re.sub(
        r'\s*<nav\b[^>]*epub:type=["\']page-list["\'][^>]*>.*?</nav>',
        "",
        nav,
        flags=re.IGNORECASE | re.DOTALL
    )

    page_nav = [
        '    <nav epub:type="page-list" hidden="hidden">',
        '      <h2>Páginas</h2>',
        '      <ol>',
    ]

    for number, target, anchor in pages:
        page_nav.append(
            f'        <li><a href="{target}#{anchor}">{number}</a></li>'
        )

    page_nav += [
        "      </ol>",
        "    </nav>"
    ]

    # Insertar después del primer nav existente.
    if re.search(r"</nav>", nav, flags=re.IGNORECASE):
        nav = re.sub(
            r"(</nav>)",
            r"\1\n" + "\n".join(page_nav),
            nav,
            count=1,
            flags=re.IGNORECASE
        )
    else:
        raise ValueError("nav.xhtml no contiene ningún elemento </nav>.")

    files[nav_name] = nav.encode("utf-8")


def update_opf_timestamp(files):
    """Actualiza dcterms:modified sin romper el XML."""
    opf_name = "content.opf"

    if opf_name not in files:
        opf_name = next(
            (n for n in files if Path(n).name.lower() == "content.opf"),
            None
        )

    if not opf_name:
        raise ValueError("El EPUB no contiene content.opf.")

    opf = files[opf_name].decode("utf-8")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    pattern = (
        r'(<meta\s+property="dcterms:modified"[^>]*>)'
        r'.*?'
        r'(</meta>)'
    )

    if re.search(pattern, opf, flags=re.IGNORECASE | re.DOTALL):
        opf = re.sub(
            pattern,
            lambda m: m.group(1) + now + m.group(2),
            opf,
            count=1,
            flags=re.IGNORECASE | re.DOTALL
        )

    files[opf_name] = opf.encode("utf-8")


def validate_xml(files):
    """Comprueba que los XML modificados siguen siendo XML válido."""
    for filename in ("content.opf", "nav.xhtml"):
        if filename in files:
            ET.fromstring(files[filename])

    for name, data in files.items():
        if name.lower().endswith((".html", ".xhtml")):
            if b'epub:type="pagebreak"' in data:
                ET.fromstring(data)


def create_epub(files, names, output):
    """Crea un EPUB válido, manteniendo mimetype sin compresión."""
    if output.exists():
        output.unlink()

    with zipfile.ZipFile(output, "w") as zout:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zout.writestr(info, files["mimetype"])

        for name in names:
            if name == "mimetype":
                continue

            zout.writestr(
                name,
                files[name],
                compress_type=zipfile.ZIP_DEFLATED
            )

    with zipfile.ZipFile(output, "r") as check:
        if check.testzip() is not None:
            raise RuntimeError("El EPUB generado contiene un archivo corrupto.")

        if check.namelist()[0] != "mimetype":
            raise RuntimeError("mimetype no es el primer archivo del EPUB.")


def main():
    parser = argparse.ArgumentParser(
        description="Añade paginación EPUB 3 aproximada a un EPUB."
    )

    parser.add_argument(
        "input",
        help="EPUB de entrada"
    )

    parser.add_argument(
        "--chars",
        type=int,
        default=1500,
        help="Caracteres visibles aproximados por página (por defecto: 1500)"
    )

    parser.add_argument(
        "--start-file",
        default=None,
        help="Archivo HTML/XHTML desde el que comienza la paginación"
    )

    parser.add_argument(
        "--output",
        default=None,
        help="EPUB de salida"
    )

    args = parser.parse_args()

    source = Path(args.input)

    if not source.exists():
        raise FileNotFoundError(f"No existe: {source}")

    if source.suffix.lower() != ".epub":
        raise ValueError("El archivo de entrada debe ser .epub.")

    if args.chars < 100:
        raise ValueError("--chars debe ser al menos 100.")

    if args.output:
        output = Path(args.output)
    else:
        output = source.with_name(
            source.stem + " - paginado.epub"
        )

    print(f"Entrada: {source}")
    print(f"Salida:  {output}")
    print(f"Caracteres/página: {args.chars}")

    with zipfile.ZipFile(source, "r") as zin:
        if "mimetype" not in zin.namelist():
            raise ValueError("No parece ser un EPUB válido: falta mimetype.")

        names = zin.namelist()
        files = {name: zin.read(name) for name in names}

    html_files = find_html_files(names)

    if not html_files:
        raise ValueError("No se han encontrado archivos HTML/XHTML de contenido.")

    print(f"Archivos de contenido encontrados: {len(html_files)}")

    pages = add_pagebreaks(
        files,
        html_files,
        args.chars,
        args.start_file
    )

    if not pages:
        raise RuntimeError(
            "No se pudieron crear páginas. "
            "Comprueba la estructura del EPUB."
        )

    update_nav(files, pages)
    update_opf_timestamp(files)
    validate_xml(files)
    create_epub(files, names, output)

    print()
    print("✓ EPUB generado correctamente")
    print(f"✓ Páginas aproximadas: {len(pages)}")
    print(f"✓ Archivo: {output}")


if __name__ == "__main__":
    main()
