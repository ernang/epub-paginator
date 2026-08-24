#!/usr/bin/env python3
"""
EPUB 3 Page Break Generator (GUI)
---------------------------------
Añade paginación aproximada EPUB 3 a un EPUB existente usando una interfaz gráfica.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import html
import re
import zipfile
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

import customtkinter as ctk
from tkinter import filedialog, messagebox

# Configurar el aspecto global
ctk.set_appearance_mode("System")  # Seguirá el modo oscuro/claro de tu PC o Mac
ctk.set_default_color_theme("blue")  # Temas: "blue", "green", "dark-blue"

# --- LÓGICA ORIGINAL DEL PROCESAMIENTO EPUB ---

def visible_text_len(fragment: str) -> int:
    text = re.sub(r"<[^>]+>", "", fragment)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return len(text.strip())

def find_html_files(names):
    candidates = [
        n for n in names
        if (n.lower().endswith((".html", ".xhtml"))
            and not n.lower().endswith("nav.xhtml")
            and "toc" not in Path(n).name.lower())
    ]
    def natural_key(name):
        parts = re.split(r"(\d+)", name)
        return [int(p) if p.isdigit() else p.lower() for p in parts]
    return sorted(candidates, key=natural_key)

def add_pagebreaks(files, html_files, chars_per_page, start_file=None):
    if start_file:
        if start_file not in html_files:
            raise ValueError(f"No se encuentra el archivo de inicio: {start_file}")
        start_index = html_files.index(start_file)
    else:
        split_files = [n for n in html_files if Path(n).name.startswith("index_split_")]
        start_index = html_files.index(split_files[0]) if split_files else 0

    page_no = 1
    accumulated = 0
    pages = []

    for name in html_files[start_index:]:
        text = files[name].decode("utf-8")
        if 'epub:type="pagebreak"' in text:
            continue

        paragraphs = list(re.finditer(r"<p\b[^>]*>.*?</p\s*>", text, flags=re.IGNORECASE | re.DOTALL))
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

            if accumulated == 0 or accumulated >= chars_per_page:
                if accumulated >= chars_per_page:
                    page_no += 1
                marker_id = f"page_{page_no}"
                marker = f'<span epub:type="pagebreak" id="{marker_id}" title="{page_no}"></span>'
                
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
    nav_name = next((n for n in files if Path(n).name.lower() == "nav.xhtml"), None) if "nav.xhtml" not in files else "nav.xhtml"
    if not nav_name:
        raise ValueError("El EPUB no contiene nav.xhtml.")

    nav = files[nav_name].decode("utf-8")
    nav = re.sub(r'\s*<nav\b[^>]*epub:type=["\']page-list["\'][^>]*>.*?</nav>', "", nav, flags=re.IGNORECASE | re.DOTALL)

    page_nav = ['    <nav epub:type="page-list" hidden="hidden">', '      <h2>Páginas</h2>', '      <ol>']
    for number, target, anchor in pages:
        page_nav.append(f'        <li><a href="{target}#{anchor}">{number}</a></li>')
    page_nav += ["      </ol>", "    </nav>"]

    if re.search(r"</nav>", nav, flags=re.IGNORECASE):
        nav = re.sub(r"(</nav>)", r"\1\n" + "\n".join(page_nav), nav, count=1, flags=re.IGNORECASE)
    else:
        raise ValueError("nav.xhtml no contiene ningún elemento </nav>.")
    files[nav_name] = nav.encode("utf-8")

def update_opf_timestamp(files):
    opf_name = next((n for n in files if Path(n).name.lower() == "content.opf"), None) if "content.opf" not in files else "content.opf"
    if not opf_name:
        raise ValueError("El EPUB no contiene content.opf.")

    opf = files[opf_name].decode("utf-8")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pattern = r'(<meta\s+property="dcterms:modified"[^>]*>).*?(</meta>)'

    if re.search(pattern, opf, flags=re.IGNORECASE | re.DOTALL):
        opf = re.sub(pattern, lambda m: m.group(1) + now + m.group(2), opf, count=1, flags=re.IGNORECASE | re.DOTALL)
    files[opf_name] = opf.encode("utf-8")

def validate_xml(files):
    for filename in ("content.opf", "nav.xhtml"):
        if filename in files:
            ET.fromstring(files[filename])
    for name, data in files.items():
        if name.lower().endswith((".html", ".xhtml")) and b'epub:type="pagebreak"' in data:
            ET.fromstring(data)

def create_epub(files, names, output):
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w") as zout:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zout.writestr(info, files["mimetype"])
        for name in names:
            if name != "mimetype":
                zout.writestr(name, files[name], compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(output, "r") as check:
        if check.testzip() is not None:
            raise RuntimeError("El EPUB generado contiene un archivo corrupto.")
        if check.namelist()[0] != "mimetype":
            raise RuntimeError("mimetype no es el primer archivo del EPUB.")

# --- INTERFAZ GRÁFICA (GUI) ---

class EpubPaginatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("EPUB 3 Page Break Generator")
        self.geometry("550x450")
        self.resizable(False, False)
        
        self.input_path = ctk.StringVar()
        self.output_path = ctk.StringVar()
        self.chars_var = ctk.IntVar(value=1500)
        self.start_file_var = ctk.StringVar()

        self.create_widgets()

    def create_widgets(self):
        # Título
        self.title_label = ctk.CTkLabel(self, text="Generador de Paginación EPUB", font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.pack(pady=(20, 15))

        # Marco principal (hace el efecto de tarjeta con bordes redondeados)
        self.main_frame = ctk.CTkFrame(self, corner_radius=15)
        self.main_frame.pack(fill="both", expand=True, padx=30, pady=(0, 30))

        # Archivo de entrada
        self.lbl_in = ctk.CTkLabel(self.main_frame, text="Archivo EPUB (Entrada):")
        self.lbl_in.pack(anchor="w", padx=20, pady=(15, 0))
        
        self.frame_in = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.frame_in.pack(fill="x", padx=20, pady=(5, 10))
        self.entry_in = ctk.CTkEntry(self.frame_in, textvariable=self.input_path, state="readonly", width=330)
        self.entry_in.pack(side="left", padx=(0, 10))
        self.btn_in = ctk.CTkButton(self.frame_in, text="Buscar", width=80, command=self.browse_input)
        self.btn_in.pack(side="right")

        # Archivo de salida
        self.lbl_out = ctk.CTkLabel(self.main_frame, text="Archivo EPUB (Salida):")
        self.lbl_out.pack(anchor="w", padx=20, pady=(5, 0))
        
        self.frame_out = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.frame_out.pack(fill="x", padx=20, pady=(5, 15))
        self.entry_out = ctk.CTkEntry(self.frame_out, textvariable=self.output_path, state="readonly", width=330)
        self.entry_out.pack(side="left", padx=(0, 10))
        self.btn_out = ctk.CTkButton(self.frame_out, text="Buscar", width=80, command=self.browse_output)
        self.btn_out.pack(side="right")

        # Opciones extra
        self.frame_opts = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.frame_opts.pack(fill="x", padx=20, pady=5)
        
        self.lbl_chars = ctk.CTkLabel(self.frame_opts, text="Caracteres por página:")
        self.lbl_chars.grid(row=0, column=0, sticky="w", pady=5)
        self.entry_chars = ctk.CTkEntry(self.frame_opts, textvariable=self.chars_var, width=100)
        self.entry_chars.grid(row=0, column=1, padx=15, sticky="w")

        self.lbl_start = ctk.CTkLabel(self.frame_opts, text="Archivo de inicio (opcional):")
        self.lbl_start.grid(row=1, column=0, sticky="w", pady=5)
        self.entry_start = ctk.CTkEntry(self.frame_opts, textvariable=self.start_file_var, width=180)
        self.entry_start.grid(row=1, column=1, padx=15, sticky="w")

        # Botón de Generar
        self.btn_generate = ctk.CTkButton(
            self, text="Generar EPUB Paginado", 
            font=ctk.CTkFont(size=14, weight="bold"), 
            height=40, corner_radius=8, fg_color="#10B981", hover_color="#059669",
            command=self.process_epub
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
        filename = filedialog.asksaveasfilename(defaultextension=".epub", filetypes=[("EPUB files", "*.epub")])
        if filename:
            self.output_path.set(filename)

    def process_epub(self):
        source_str = self.input_path.get()
        out_str = self.output_path.get()
        
        if not source_str:
            messagebox.showwarning("Faltan datos", "Por favor, selecciona un archivo EPUB de entrada.")
            return
            
        source = Path(source_str)
        output = Path(out_str)
        chars = self.chars_var.get()
        start_file = self.start_file_var.get() if self.start_file_var.get().strip() else None

        if not source.exists():
            messagebox.showerror("Error", f"No existe el archivo: {source}")
            return
        if chars < 100:
            messagebox.showerror("Error", "Los caracteres por página deben ser al menos 100.")
            return

        self.btn_generate.configure(text="Procesando...", state="disabled")
        self.update() # Refrescar la interfaz

        try:
            with zipfile.ZipFile(source, "r") as zin:
                if "mimetype" not in zin.namelist():
                    raise ValueError("No parece ser un EPUB válido: falta mimetype.")
                names = zin.namelist()
                files = {name: zin.read(name) for name in names}

            html_files = find_html_files(names)
            if not html_files:
                raise ValueError("No se han encontrado archivos HTML/XHTML de contenido.")

            pages = add_pagebreaks(files, html_files, chars, start_file)
            if not pages:
                raise RuntimeError("No se pudieron crear páginas. Comprueba la estructura del EPUB.")

            update_nav(files, pages)
            update_opf_timestamp(files)
            validate_xml(files)
            create_epub(files, names, output)

            messagebox.showinfo("Éxito", f"EPUB generado correctamente.\n\nPáginas creadas: {len(pages)}\nGuardado en:\n{output.name}")

        except Exception as e:
            messagebox.showerror("Error durante el proceso", str(e))
        finally:
            self.btn_generate.configure(text="Generar EPUB Paginado", state="normal")

if __name__ == "__main__":
    app = EpubPaginatorApp()
    app.mainloop()