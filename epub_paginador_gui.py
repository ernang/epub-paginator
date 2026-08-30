#!/usr/bin/env python3
"""
EPUB 3 Page Break Generator (GUI)
---------------------------------
Añade paginación aproximada EPUB 3 a un EPUB existente usando una interfaz gráfica.
"""

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from tkinter import ttk, filedialog, messagebox
from urllib.parse import unquote
import customtkinter as ctk
import html
import posixpath
import re
import tkinter as tk
import xml.etree.ElementTree as ET
import zipfile

# Configurar el aspecto global
ctk.set_appearance_mode("System")  # Seguirá el modo oscuro/claro de tu PC o Mac
ctk.set_default_color_theme("blue")  # Temas: "blue", "green", "dark-blue"

# --- LÓGICA DE PROCESAMIENTO EPUB 2 Y EPUB 3 ---
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"
XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"

ET.register_namespace("", OPF_NS)
ET.register_namespace("dc", DC_NS)
ET.register_namespace("", NCX_NS)


def normalise_zip_path(path):
    """
    Normaliza rutas internas del EPUB utilizando siempre barras /.
    """
    return posixpath.normpath(str(path).replace("\\", "/")).lstrip("/")


def decode_text(data):
    """
    Decodifica un documento de texto del EPUB.
    EPUB utiliza normalmente UTF-8, pero algunos EPUB antiguos tienen
    archivos codificados como Windows-1252.
    """
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("windows-1252")
        text = re.sub(
            r'(<\?xml\b[^>]*encoding=["\'])[^"\']+(["\'])',
            r"\1utf-8\2",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
        return text


def xml_root(data, filename):
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"El archivo XML «{filename}» no es válido:\n{exc}") from exc


def local_name(tag):
    """
    Devuelve el nombre de una etiqueta sin su espacio de nombres.
    """
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def find_opf(files):
    """
    Localiza el OPF leyendo META-INF/container.xml.

    Si container.xml está dañado, intenta localizar un OPF existente
    como medida de compatibilidad.
    """
    container_name = next(
        (name for name in files if name.lower() == "meta-inf/container.xml"),
        None,
    )

    if container_name:
        root = xml_root(files[container_name], container_name)

        rootfile = root.find(f".//{{{CONTAINER_NS}}}rootfile")
        if rootfile is None:
            rootfile = next(
                (
                    element
                    for element in root.iter()
                    if local_name(element.tag) == "rootfile"
                ),
                None,
            )

        if rootfile is not None:
            full_path = rootfile.get("full-path")
            if full_path:
                full_path = normalise_zip_path(unquote(full_path))

                if full_path in files:
                    return full_path

                lower_names = {name.lower(): name for name in files}

                if full_path.lower() in lower_names:
                    return lower_names[full_path.lower()]

    opf_candidates = [name for name in files if name.lower().endswith(".opf")]

    if len(opf_candidates) == 1:
        return opf_candidates[0]

    if not opf_candidates:
        raise ValueError("El EPUB no contiene ningún archivo OPF.")

    raise ValueError("No se ha podido determinar cuál es el archivo OPF principal.")


def read_package_info(files):
    """
    Lee la versión, el manifiesto y el spine del EPUB.
    """
    opf_name = find_opf(files)
    root = xml_root(files[opf_name], opf_name)

    version_text = root.get("version", "2.0").strip()
    try:
        major_version = int(version_text.split(".", 1)[0])
    except ValueError:
        major_version = 2

    opf_dir = posixpath.dirname(opf_name)

    manifest = {}
    item_elements = {}

    for element in root.iter():
        if local_name(element.tag) != "item":
            continue

        item_id = element.get("id")
        href = element.get("href")

        if not item_id or not href:
            continue

        href_without_fragment = unquote(href.split("#", 1)[0])
        full_path = normalise_zip_path(posixpath.join(opf_dir, href_without_fragment))

        manifest[item_id] = {
            "id": item_id,
            "href": href,
            "path": full_path,
            "media_type": element.get("media-type", ""),
            "properties": set(element.get("properties", "").split()),
        }
        item_elements[item_id] = element

    spine = next(
        (element for element in root.iter() if local_name(element.tag) == "spine"),
        None,
    )

    spine_ids = []
    if spine is not None:
        for element in spine:
            if local_name(element.tag) == "itemref":
                idref = element.get("idref")
                if idref:
                    spine_ids.append(idref)

    return {
        "opf_name": opf_name,
        "opf_dir": opf_dir,
        "root": root,
        "version": version_text,
        "major_version": major_version,
        "manifest": manifest,
        "item_elements": item_elements,
        "spine": spine,
        "spine_ids": spine_ids,
    }


def find_content_files(files, package):
    """
    Obtiene los capítulos en el orden real de lectura indicado por el spine.
    """
    result = []

    for item_id in package["spine_ids"]:
        item = package["manifest"].get(item_id)
        if not item:
            continue

        path = item["path"]
        media_type = item["media_type"].lower()

        is_html = media_type in {
            "application/xhtml+xml",
            "text/html",
        } or path.lower().endswith((".xhtml", ".html", ".htm"))

        if is_html and path in files:
            result.append(path)

    if result:
        return result

    # Compatibilidad con EPUB cuyo spine está incompleto o dañado.
    excluded_names = {
        "nav.xhtml",
        "toc.xhtml",
        "toc.html",
    }

    candidates = [
        name
        for name in files
        if name.lower().endswith((".xhtml", ".html", ".htm"))
        and PurePosixPath(name).name.lower() not in excluded_names
    ]

    def natural_key(name):
        parts = re.split(r"(\d+)", name)
        return [int(part) if part.isdigit() else part.lower() for part in parts]

    return sorted(candidates, key=natural_key)


def resolve_start_file(start_file, html_files):
    """
    Permite indicar la ruta completa o únicamente el nombre del capítulo.
    """
    if not start_file:
        split_files = [
            name
            for name in html_files
            if PurePosixPath(name).name.startswith("index_split_")
        ]

        if split_files:
            return html_files.index(split_files[0])

        return 0

    wanted = normalise_zip_path(start_file.strip())

    if wanted in html_files:
        return html_files.index(wanted)

    basename_matches = [
        name
        for name in html_files
        if PurePosixPath(name).name.lower() == PurePosixPath(wanted).name.lower()
    ]

    if len(basename_matches) == 1:
        return html_files.index(basename_matches[0])

    if len(basename_matches) > 1:
        raise ValueError(
            "Hay varios archivos con ese nombre. " "Indica la ruta interna completa."
        )

    raise ValueError(f"No se encuentra el archivo de inicio: {start_file}")


def visible_text_len(fragment):
    text = re.sub(
        r"<(?:script|style)\b[^>]*>.*?</(?:script|style)\s*>",
        "",
        fragment,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return len(text.strip())


def ensure_epub_namespace(text):
    """
    Añade xmlns:epub al elemento html cuando no está declarado.
    """
    if re.search(
        r"\bxmlns:epub\s*=",
        text,
        flags=re.IGNORECASE,
    ):
        return text

    return re.sub(
        r"<html\b",
        f'<html xmlns:epub="{EPUB_NS}"',
        text,
        count=1,
        flags=re.IGNORECASE,
    )


def add_pagebreaks(
    files,
    html_files,
    chars_per_page,
    epub_major_version=3,
    start_file=None,
):
    """
    Inserta saltos de página contando el texto visible real.

    No depende de que el EPUB utilice etiquetas <p>.
    Funciona también con texto dentro de div, section, blockquote,
    headings y otros elementos XHTML.
    """

    start_index = resolve_start_file(start_file, html_files)

    page_no = 1
    accumulated = 0
    pages = []

    # Separa etiquetas HTML/XML del contenido de texto.
    token_pattern = re.compile(
        r"("
        r"<!\[CDATA\[.*?\]\]>"
        r"|<!--.*?-->"
        r"|<\?.*?\?>"
        r"|<![^>]*>"
        r"|<[^>]+>"
        r")",
        flags=re.DOTALL,
    )

    # Etiquetas cuyo texto no debe contar como contenido del libro.
    ignored_elements = {
        "head",
        "title",
        "style",
        "script",
        "noscript",
    }

    for name in html_files[start_index:]:
        original_text = decode_text(files[name])

        # Elimina únicamente marcadores generados anteriormente por
        # esta aplicación. Así se puede volver a procesar el EPUB.
        text = re.sub(
            r'<span\b[^>]*\bid=["\']page_\d+["\'][^>]*>' r"\s*</span\s*>",
            "",
            original_text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        tokens = token_pattern.split(text)

        result = []
        inside_body = False
        ignored_depth = 0
        file_modified = False

        for token in tokens:
            if not token:
                continue

            # El token es una etiqueta, comentario o declaración.
            if token.startswith("<"):
                result.append(token)

                tag_match = re.match(
                    r"<\s*(/?)\s*" r"(?:[A-Za-z_][\w.-]*:)?" r"([A-Za-z_][\w.-]*)",
                    token,
                    flags=re.IGNORECASE,
                )

                if not tag_match:
                    continue

                is_closing = bool(tag_match.group(1))
                tag_name = tag_match.group(2).lower()

                is_self_closing = bool(re.search(r"/\s*>$", token))

                if tag_name == "body":
                    if is_closing:
                        inside_body = False
                    else:
                        inside_body = True
                    continue

                if tag_name in ignored_elements:
                    if is_closing:
                        ignored_depth = max(0, ignored_depth - 1)
                    elif not is_self_closing:
                        ignored_depth += 1

                continue

            # Texto fuera de body o dentro de style/script/head.
            if not inside_body or ignored_depth > 0:
                result.append(token)
                continue

            # Conserva espacios y saltos de línea exactamente.
            parts = re.split(r"(\s+)", token)

            for part in parts:
                if not part:
                    continue

                # Los espacios se conservan, pero no crean una página.
                if part.isspace():
                    result.append(part)
                    continue

                visible_length = visible_text_len(part)

                if visible_length == 0:
                    result.append(part)
                    continue

                # La primera página se coloca antes del primer texto.
                # Las siguientes, antes de la palabra posterior al límite.
                if not pages or accumulated >= chars_per_page:
                    if pages:
                        page_no += 1

                    marker_id = f"page_{page_no}"

                    if epub_major_version >= 3:
                        marker = (
                            f'<span epub:type="pagebreak" '
                            f'role="doc-pagebreak" '
                            f'class="pagebreak" '
                            f'id="{marker_id}" '
                            f'title="{page_no}" '
                            f'aria-label="Página {page_no}">'
                            f"</span>"
                        )
                    else:
                        marker = (
                            f'<span class="pagebreak" '
                            f'id="{marker_id}" '
                            f'title="{page_no}">'
                            f"</span>"
                        )

                    result.append(marker)

                    pages.append(
                        (
                            page_no,
                            name,
                            marker_id,
                        )
                    )

                    accumulated = 0
                    file_modified = True

                result.append(part)
                accumulated += visible_length

        if file_modified:
            updated_text = "".join(result)

            if epub_major_version >= 3:
                updated_text = ensure_epub_namespace(updated_text)

            files[name] = updated_text.encode("utf-8")

    return pages


def relative_href(from_document, target_document, anchor=None):
    """
    Crea un enlace relativo entre dos archivos internos del EPUB.
    """
    source_dir = posixpath.dirname(from_document) or "."
    href = posixpath.relpath(target_document, source_dir)

    if anchor:
        href += f"#{anchor}"

    return href


def find_nav_document(package, files):
    """
    Localiza el documento de navegación EPUB 3 mediante properties="nav".
    También admite EPUB que no lo declara correctamente en el OPF.
    """
    for item in package["manifest"].values():
        if "nav" in item["properties"] and item["path"] in files:
            return item["path"]

    possible_names = {
        "nav.xhtml",
        "navigation.xhtml",
        "toc.xhtml",
    }

    for name in files:
        if PurePosixPath(name).name.lower() in possible_names:
            text = decode_text(files[name])
            if (
                'epub:type="toc"' in text
                or "epub:type='toc'" in text
                or 'epub:type="page-list"' in text
                or "epub:type='page-list'" in text
            ):
                return name

    return None


def create_nav_document(files, package):
    """
    Crea un documento de navegación cuando el EPUB 3 no tiene ninguno.
    """
    nav_name = normalise_zip_path(posixpath.join(package["opf_dir"], "nav.xhtml"))

    counter = 1
    while nav_name in files:
        nav_name = normalise_zip_path(
            posixpath.join(
                package["opf_dir"],
                f"nav_{counter}.xhtml",
            )
        )
        counter += 1

    nav_text = f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="{XHTML_NS}" xmlns:epub="{EPUB_NS}">
  <head>
    <title>Navegación</title>
  </head>
  <body>
    <nav epub:type="toc" id="toc">
      <h1>Contenido</h1>
      <ol></ol>
    </nav>
  </body>
</html>
"""

    files[nav_name] = nav_text.encode("utf-8")

    manifest_element = next(
        (
            element
            for element in package["root"].iter()
            if local_name(element.tag) == "manifest"
        ),
        None,
    )

    if manifest_element is None:
        raise ValueError("El OPF no contiene el elemento manifest.")

    existing_ids = set(package["manifest"])
    nav_id = "nav"

    counter = 1
    while nav_id in existing_ids:
        nav_id = f"nav_{counter}"
        counter += 1

    href = posixpath.relpath(nav_name, package["opf_dir"] or ".")

    item_element = ET.SubElement(
        manifest_element,
        f"{{{OPF_NS}}}item",
        {
            "id": nav_id,
            "href": href,
            "media-type": "application/xhtml+xml",
            "properties": "nav",
        },
    )

    package["manifest"][nav_id] = {
        "id": nav_id,
        "href": href,
        "path": nav_name,
        "media_type": "application/xhtml+xml",
        "properties": {"nav"},
    }
    package["item_elements"][nav_id] = item_element

    return nav_name


def update_nav_document(files, nav_name, pages):
    nav_text = decode_text(files[nav_name])

    nav_text = ensure_epub_namespace(nav_text)

    page_list_pattern = re.compile(
        r"<nav\b[^>]*\bepub:type\s*=\s*"
        r'(["\'])page-list\1[^>]*>'
        r".*?"
        r"</nav\s*>",
        flags=re.IGNORECASE | re.DOTALL,
    )

    nav_text = page_list_pattern.sub("", nav_text)

    lines = [
        '    <nav epub:type="page-list" ' 'id="page-list" hidden="hidden">',
        "      <h2>Páginas</h2>",
        "      <ol>",
    ]

    # for number, target, anchor in pages:
    #     href = relative_href(nav_name, target, anchor)
    #     lines.append(
    #         f"        <li>{html.escape(href, quote=True)}" f"{number}</a></li>"
    #     )
    for number, target, anchor in pages:
        href = relative_href(nav_name, target, anchor)

        lines.append(f"        <li><a>{html.escape(href, quote=True)}{number}</a></li>")

    lines.extend(
        [
            "      </ol>",
            "    </nav>",
        ]
    )

    page_navigation = "\n".join(lines)

    body_close = re.search(
        r"</(?:[A-Za-z_][\w.-]*:)?body\s*>",
        nav_text,
        flags=re.IGNORECASE,
    )

    if not body_close:
        raise ValueError(
            f"El documento de navegación «{nav_name}» " "no contiene </body>."
        )

    insert_at = body_close.start()
    nav_text = nav_text[:insert_at] + page_navigation + "\n" + nav_text[insert_at:]

    files[nav_name] = nav_text.encode("utf-8")


def find_ncx_document(package, files):
    """
    Localiza toc.ncx mediante el manifiesto o el atributo toc del spine.
    """
    if package["spine"] is not None:
        toc_id = package["spine"].get("toc")
        if toc_id:
            item = package["manifest"].get(toc_id)
            if item and item["path"] in files:
                return item["path"]

    for item in package["manifest"].values():
        if (
            item["media_type"].lower() == "application/x-dtbncx+xml"
            and item["path"] in files
        ):
            return item["path"]

    for name in files:
        if name.lower().endswith(".ncx"):
            return name

    return None


def update_ncx(files, ncx_name, pages):
    """
    Añade o reemplaza pageList en toc.ncx para EPUB 2.
    """
    root = xml_root(files[ncx_name], ncx_name)

    for parent in root.iter():
        for child in list(parent):
            if local_name(child.tag) == "pageList":
                parent.remove(child)

    max_play_order = 0

    for element in root.iter():
        value = element.get("playOrder")
        if value and value.isdigit():
            max_play_order = max(max_play_order, int(value))

    namespace = ""
    if root.tag.startswith("{"):
        namespace = root.tag.split("}", 1)[0][1:]

    def tag(name):
        return f"{{{namespace}}}{name}" if namespace else name

    page_list = ET.Element(tag("pageList"), {"id": "page-list"})

    nav_label = ET.SubElement(page_list, tag("navLabel"))
    ET.SubElement(nav_label, tag("text")).text = "Páginas"

    for offset, (number, target, anchor) in enumerate(pages, start=1):
        page_target = ET.SubElement(
            page_list,
            tag("pageTarget"),
            {
                "id": f"pageTarget_{number}",
                "type": "normal",
                "value": str(number),
                "playOrder": str(max_play_order + offset),
            },
        )

        label = ET.SubElement(page_target, tag("navLabel"))
        ET.SubElement(label, tag("text")).text = str(number)

        content = ET.SubElement(page_target, tag("content"))
        content.set(
            "src",
            relative_href(ncx_name, target, anchor),
        )

    nav_map_index = None
    children = list(root)

    for index, child in enumerate(children):
        if local_name(child.tag) == "navMap":
            nav_map_index = index
            break

    if nav_map_index is None:
        root.append(page_list)
    else:
        root.insert(nav_map_index, page_list)

    files[ncx_name] = ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )


def update_opf(files, package):
    """
    Guarda los cambios del OPF y actualiza dcterms:modified en EPUB 3.
    """
    root = package["root"]

    if package["major_version"] >= 3:
        metadata = next(
            (
                element
                for element in root.iter()
                if local_name(element.tag) == "metadata"
            ),
            None,
        )

        if metadata is not None:
            modified_element = next(
                (
                    element
                    for element in metadata
                    if (
                        local_name(element.tag) == "meta"
                        and element.get("property") == "dcterms:modified"
                    )
                ),
                None,
            )

            if modified_element is None:
                modified_element = ET.SubElement(
                    metadata,
                    f"{{{OPF_NS}}}meta",
                    {"property": "dcterms:modified"},
                )

            modified_element.text = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

    files[package["opf_name"]] = ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )


def update_navigation(files, package, pages):
    """
    Actualiza la navegación correspondiente a cada versión.
    """
    nav_name = find_nav_document(package, files)
    ncx_name = find_ncx_document(package, files)

    if package["major_version"] >= 3:
        if nav_name is None:
            nav_name = create_nav_document(files, package)

        update_nav_document(files, nav_name, pages)

        # Algunos EPUB 3 también conservan un NCX por compatibilidad.
        if ncx_name:
            update_ncx(files, ncx_name, pages)

    else:
        # EPUB 2 utiliza normalmente toc.ncx.
        if ncx_name:
            update_ncx(files, ncx_name, pages)
        else:
            # EPUB 2 sin NCX: los marcadores se crean igualmente.
            # No se fuerza una conversión insegura a EPUB 3.
            print(
                "Aviso: el EPUB 2 no contiene toc.ncx. "
                "Se han añadido los marcadores, pero no pageList."
            )


def validate_xml(files, package):
    """
    Valida los principales documentos modificados.
    """
    files_to_validate = {package["opf_name"]}

    nav_name = find_nav_document(package, files)
    ncx_name = find_ncx_document(package, files)

    if nav_name:
        files_to_validate.add(nav_name)

    if ncx_name:
        files_to_validate.add(ncx_name)

    for name, data in files.items():
        if name.lower().endswith((".html", ".xhtml")) and (
            b'epub:type="pagebreak"' in data
            or b'role="doc-pagebreak"' in data
            or b'class="pagebreak"' in data
        ):
            files_to_validate.add(name)

    for filename in files_to_validate:
        if filename in files:
            try:
                ET.fromstring(files[filename])
            except ET.ParseError as exc:
                raise ValueError(
                    f"El archivo modificado «{filename}» " f"no es XML válido:\n{exc}"
                ) from exc


def create_epub(files, original_names, output):
    """
    Crea el EPUB respetando la regla de que mimetype sea el primer
    archivo y no se comprima.
    """
    if output.exists():
        output.unlink()

    all_names = list(original_names)

    # Incluye archivos nuevos, por ejemplo un nav.xhtml recién creado.
    for name in files:
        if name not in all_names:
            all_names.append(name)

    mimetype = files.get("mimetype", b"application/epub+zip")

    if mimetype.strip() != b"application/epub+zip":
        raise ValueError("El archivo mimetype no contiene application/epub+zip.")

    with zipfile.ZipFile(output, "w") as zout:
        mimetype_info = zipfile.ZipInfo("mimetype")
        mimetype_info.compress_type = zipfile.ZIP_STORED
        zout.writestr(mimetype_info, b"application/epub+zip")

        for name in all_names:
            if name == "mimetype":
                continue

            if name not in files:
                continue

            zout.writestr(
                name,
                files[name],
                compress_type=zipfile.ZIP_DEFLATED,
            )

    with zipfile.ZipFile(output, "r") as check:
        corrupt_file = check.testzip()

        if corrupt_file is not None:
            raise RuntimeError(f"El EPUB contiene un archivo corrupto: {corrupt_file}")

        names = check.namelist()

        if not names or names[0] != "mimetype":
            raise RuntimeError("mimetype no es el primer archivo del EPUB.")

        info = check.getinfo("mimetype")
        if info.compress_type != zipfile.ZIP_STORED:
            raise RuntimeError("El archivo mimetype está comprimido.")


# --- INTERFAZ GRÁFICA (GUI) ---


class EpubPaginatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("EPUB 3 Page Break Generator")
        self.geometry("800x600")
        self.minsize(700, 500)
        self.resizable(True, True)

        self.input_path = ctk.StringVar()
        self.output_path = ctk.StringVar()
        self.chars_var = ctk.IntVar(value=1500)
        self.start_file_var = ctk.StringVar()

        self.create_widgets()

    def create_widgets(self):
        # Título
        self.title_label = ctk.CTkLabel(
            self, text="📚 EPUB Paginator", font=ctk.CTkFont(size=28, weight="bold")
        )
        self.title_label.pack(pady=(20, 15))
        self.subtitle_label = ctk.CTkLabel(
            self,
            text="Genera paginación EPUB 2 y EPUB 3 automáticamente",
            text_color=("gray40", "gray70"),
            font=ctk.CTkFont(size=13),
        )

        self.subtitle_label.pack(pady=(0, 20))

        # Marco principal (hace el efecto de tarjeta con bordes redondeados)
        self.main_frame = ctk.CTkFrame(
            self,
            corner_radius=20,
            border_width=1,
        )
        self.main_frame.pack(fill="both", expand=True, padx=30, pady=(0, 30))

        # Archivo de entrada
        self.lbl_in = ctk.CTkLabel(self.main_frame, text="Archivo EPUB (Entrada):")
        self.lbl_in.pack(anchor="w", padx=20, pady=(15, 0))

        self.frame_in = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.frame_in.pack(fill="x", padx=20, pady=(5, 10))
        self.entry_in = ctk.CTkEntry(
            self.frame_in,
            textvariable=self.input_path,
            border_width=1,
            fg_color=("gray92", "gray18"),
        )
        self.entry_in.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.btn_in = ctk.CTkButton(
            self.frame_in, text="📂 Abrir", width=100, command=self.browse_input
        )
        self.btn_in.pack(side="right")

        # Archivo de salida
        self.lbl_out = ctk.CTkLabel(self.main_frame, text="Archivo EPUB (Salida):")
        self.lbl_out.pack(anchor="w", padx=20, pady=(5, 0))

        self.frame_out = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.frame_out.pack(fill="x", padx=20, pady=(5, 15))
        self.entry_out = ctk.CTkEntry(
            self.frame_out,
            textvariable=self.output_path,
            border_width=1,
            fg_color=("gray92", "gray18"),
        )
        self.entry_out.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.btn_out = ctk.CTkButton(
            self.frame_out, text="💾 Guardar", width=100, command=self.browse_output
        )
        self.btn_out.pack(side="right")

        # Opciones extra
        # Tarjeta de configuración
        self.config_card = ctk.CTkFrame(
            self.main_frame, corner_radius=15, border_width=1
        )

        self.config_card.pack(fill="x", padx=20, pady=(10, 15))
        self.config_title = ctk.CTkLabel(
            self.config_card,
            text="⚙️ Configuración",
            font=ctk.CTkFont(size=16, weight="bold"),
        )

        self.config_title.pack(anchor="w", padx=15, pady=(12, 5))

        self.frame_opts = ctk.CTkFrame(self.config_card, fg_color="transparent")

        self.frame_opts.pack(fill="x", padx=15, pady=(0, 12))

        self.frame_opts.grid_columnconfigure(1, weight=1)

        # Carácteres por página
        self.lbl_chars = ctk.CTkLabel(self.frame_opts, text="Caracteres por página")

        self.lbl_chars.grid(row=0, column=0, sticky="w", pady=(0, 8))

        self.entry_chars = ctk.CTkEntry(self.frame_opts, textvariable=self.chars_var)

        self.entry_chars.grid(row=0, column=1, sticky="ew", padx=(15, 0), pady=(0, 8))

        # Archivo de inicio
        self.lbl_start = ctk.CTkLabel(
            self.frame_opts, text="Archivo de inicio (opcional)"
        )

        self.lbl_start.grid(row=1, column=0, sticky="w")

        self.entry_start = ctk.CTkEntry(
            self.frame_opts, textvariable=self.start_file_var
        )

        self.entry_start.grid(row=1, column=1, sticky="ew", padx=(15, 0))

        # Botón de Generar
        self.btn_generate = ctk.CTkButton(
            self,
            text="Generar EPUB Paginado",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
            corner_radius=8,
            fg_color="#10B981",
            hover_color="#059669",
            command=self.process_epub,
        )
        self.btn_generate.pack(pady=(0, 25))

    def browse_input(self):
        filename = filedialog.askopenfilename(filetypes=[("EPUB files", "*.epub")])
        if filename:
            self.input_path.set(filename)
            # Autocompletar la salida
            in_path = Path(filename)
            out_path = in_path.with_name(in_path.stem + " - paginado.epub")
            self.output_path.set(str(out_path))

    def browse_output(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".epub", filetypes=[("EPUB files", "*.epub")]
        )
        if filename:
            self.output_path.set(filename)

    # def process_epub(self):
    #     source_str = self.input_path.get()
    #     out_str = self.output_path.get()

    #     if not source_str:
    #         messagebox.showwarning("Faltan datos", "Por favor, selecciona un archivo EPUB de entrada.")
    #         return

    #     source = Path(source_str)
    #     output = Path(out_str)
    #     chars = self.chars_var.get()
    #     start_file = self.start_file_var.get() if self.start_file_var.get().strip() else None

    #     if not source.exists():
    #         messagebox.showerror("Error", f"No existe el archivo: {source}")
    #         return
    #     if chars < 100:
    #         messagebox.showerror("Error", "Los caracteres por página deben ser al menos 100.")
    #         return

    #     self.btn_generate.configure(text="Procesando...", state="disabled")
    #     self.update() # Refrescar la interfaz

    #     try:
    #         with zipfile.ZipFile(source, "r") as zin:
    #             if "mimetype" not in zin.namelist():
    #                 raise ValueError("No parece ser un EPUB válido: falta mimetype.")
    #             names = zin.namelist()
    #             files = {name: zin.read(name) for name in names}

    #         html_files = find_html_files(names)
    #         if not html_files:
    #             raise ValueError("No se han encontrado archivos HTML/XHTML de contenido.")

    #         pages = add_pagebreaks(files, html_files, chars, start_file)
    #         if not pages:
    #             raise RuntimeError("No se pudieron crear páginas. Comprueba la estructura del EPUB.")

    #         update_nav(files, pages)
    #         update_opf_timestamp(files)
    #         validate_xml(files)
    #         create_epub(files, names, output)

    #         messagebox.showinfo("Éxito", f"EPUB generado correctamente.\n\nPáginas creadas: {len(pages)}\nGuardado en:\n{output.name}")

    #     except Exception as e:
    #         messagebox.showerror("Error durante el proceso", str(e))
    #     finally:
    #         self.btn_generate.configure(text="Generar EPUB Paginado", state="normal")
    def process_epub(self):
        source_str = self.input_path.get().strip()
        output_str = self.output_path.get().strip()

        if not source_str:
            messagebox.showwarning(
                "Faltan datos",
                "Selecciona un archivo EPUB de entrada.",
            )
            return

        if not output_str:
            messagebox.showwarning(
                "Faltan datos",
                "Selecciona un archivo EPUB de salida.",
            )
            return

        source = Path(source_str)
        output = Path(output_str)

        try:
            chars = int(self.chars_var.get())
        except (TypeError, ValueError, tk.TclError):
            messagebox.showerror(
                "Error",
                "Los caracteres por página deben ser un número entero.",
            )
            return

        start_file_text = self.start_file_var.get().strip()
        start_file = start_file_text or None

        if not source.exists():
            messagebox.showerror(
                "Error",
                f"No existe el archivo:\n{source}",
            )
            return

        if not source.is_file():
            messagebox.showerror(
                "Error",
                "La ruta de entrada no corresponde a un archivo.",
            )
            return

        if chars < 100:
            messagebox.showerror(
                "Error",
                "Los caracteres por página deben ser al menos 100.",
            )
            return

        try:
            if source.resolve() == output.resolve():
                messagebox.showerror(
                    "Error",
                    "El archivo de salida debe ser distinto " "del archivo de entrada.",
                )
                return
        except OSError:
            pass

        self.btn_generate.configure(
            text="Procesando...",
            state="disabled",
        )
        self.update_idletasks()

        try:
            with zipfile.ZipFile(source, "r") as zin:
                archive_names = zin.namelist()

                if "mimetype" not in archive_names:
                    raise ValueError("No parece ser un EPUB válido: falta mimetype.")

                if zin.read("mimetype").strip() != b"application/epub+zip":
                    raise ValueError("El archivo mimetype del EPUB no es válido.")

                files = {
                    name: zin.read(name)
                    for name in archive_names
                    if not name.endswith("/")
                }

            package = read_package_info(files)
            html_files = find_content_files(files, package)

            if not html_files:
                raise ValueError(
                    "No se han encontrado capítulos HTML o XHTML "
                    "en el spine del EPUB."
                )

            pages = add_pagebreaks(
                files=files,
                html_files=html_files,
                chars_per_page=chars,
                epub_major_version=package["major_version"],
                start_file=start_file,
            )

            if not pages:
                raise RuntimeError(
                    "No se pudieron crear páginas. "
                    "El EPUB puede estar ya paginado o no utilizar "
                    "párrafos <p>."
                )

            update_navigation(files, package, pages)
            update_opf(files, package)
            validate_xml(files, package)

            output.parent.mkdir(parents=True, exist_ok=True)
            create_epub(files, archive_names, output)

            navigation_type = "EPUB 3" if package["major_version"] >= 3 else "EPUB 2"

            messagebox.showinfo(
                "Éxito",
                "EPUB generado correctamente.\n\n"
                f"Formato detectado: {navigation_type}\n"
                f"Páginas creadas: {len(pages)}\n"
                f"Guardado en:\n{output}",
            )

        except zipfile.BadZipFile:
            messagebox.showerror(
                "EPUB no válido",
                "El archivo seleccionado no es un ZIP/EPUB válido.",
            )

        except PermissionError:
            messagebox.showerror(
                "Permiso denegado",
                "No se puede escribir el archivo de salida. "
                "Comprueba que no esté abierto en otro programa.",
            )

        except Exception as exc:
            messagebox.showerror(
                "Error durante el proceso",
                str(exc),
            )

        finally:
            self.btn_generate.configure(
                text="Generar EPUB Paginado",
                state="normal",
            )


if __name__ == "__main__":
    app = EpubPaginatorApp()
    app.mainloop()
