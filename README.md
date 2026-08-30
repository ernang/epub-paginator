# EPUB Page Break Generator

Aplicación de escritorio en Python para añadir una paginación aproximada a archivos EPUB 2 y EPUB 3 mediante una interfaz gráfica moderna.

El programa analiza el texto visible del libro, inserta marcadores de página y actualiza los documentos de navegación internos del EPUB. El archivo original no se modifica: el resultado se guarda como un nuevo EPUB.

## Características

- Interfaz gráfica creada con `CustomTkinter`.
- Compatible con EPUB 2 y EPUB 3.
- Calcula páginas aproximadas según la cantidad de caracteres visibles.
- Respeta el orden de lectura definido en el `spine` del EPUB.
- Permite seleccionar el archivo o capítulo desde el que debe comenzar la paginación.
- Ignora etiquetas HTML, estilos y scripts al contar caracteres.
- Añade marcadores de salto de página al contenido XHTML.
- Actualiza la navegación del libro:
  - Documento `nav.xhtml` en EPUB 3.
  - Lista de páginas de `toc.ncx` en EPUB 2.
- Crea un documento de navegación si el EPUB 3 no dispone de uno.
- Actualiza la fecha de modificación del paquete EPUB 3.
- Conserva la estructura interna del EPUB.
- Guarda `mimetype` como primer archivo y sin compresión, tal como requiere el formato EPUB.
- Admite documentos codificados en UTF-8 y Windows-1252.
- Se adapta al modo claro u oscuro configurado en el sistema.
- Ventana redimensionable.

## Requisitos

- Python 3.10 o posterior recomendado.
- `customtkinter`.
- `tkinter`, incluido normalmente con Python en Windows y macOS.

El resto de módulos utilizados forman parte de la biblioteca estándar de Python.

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/TU_USUARIO/TU_REPOSITORIO.git
cd TU_REPOSITORIO
```

También puedes descargar el repositorio como archivo ZIP desde GitHub y descomprimirlo.

### 2. Crear un entorno virtual

#### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

#### macOS o Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instalar las dependencias

```bash
python -m pip install -r requirements.txt
```

Si todavía no tienes un archivo `requirements.txt`, créalo con este contenido:

```text
customtkinter
```

En Windows también puedes instalar la dependencia directamente con:

```powershell
py -m pip install customtkinter
```

## Uso

Ejecuta la aplicación desde la carpeta del proyecto.

### Windows

```powershell
py epub_paginador_gui.py
```

### macOS o Linux

```bash
python3 epub_paginador_gui.py
```

Después:

1. Selecciona el archivo EPUB que quieres procesar.
2. Configura la cantidad aproximada de caracteres por página.
3. Si lo necesitas, indica el capítulo desde el que debe comenzar la paginación.
4. Selecciona la ubicación del archivo de salida.
5. Inicia el proceso.
6. Abre el nuevo EPUB en tu lector habitual para comprobar el resultado.

## ¿Cómo funciona?

El programa abre el EPUB como un archivo ZIP y localiza su paquete OPF mediante `META-INF/container.xml`. A continuación, obtiene los capítulos siguiendo el orden definido en el `spine`.

Para calcular las páginas, elimina temporalmente del recuento las etiquetas HTML, los estilos y los scripts. Después cuenta el texto visible e inserta marcadores de página según el valor configurado de caracteres por página.

Finalmente, actualiza la navegación correspondiente a la versión del EPUB, valida los documentos XML principales y vuelve a empaquetar el libro.

## Paginación aproximada

La paginación generada no representa necesariamente las páginas físicas de una edición impresa. El número de páginas depende del valor de caracteres por página y de la estructura interna de cada EPUB.

Dos libros con una longitud parecida pueden producir cantidades de páginas diferentes si utilizan capítulos, etiquetas o estructuras XHTML distintas.

Para obtener un resultado más cercano a una edición concreta, ajusta el número de caracteres por página y vuelve a generar el EPUB.

## Compatibilidad

El programa está pensado para trabajar con:

- EPUB 2 con navegación NCX.
- EPUB 3 con documento de navegación XHTML.
- EPUB que contienen capítulos XHTML o HTML declarados en el manifiesto.
- EPUB con rutas internas relativas y nombres de archivo codificados.

Algunos EPUB con una estructura dañada, XML no válido, contenido cifrado o gestión de derechos digitales pueden no procesarse correctamente.

## Estructura recomendada del repositorio

```text
.
├── epub_paginador_gui.py
├── requirements.txt
├── README.md
├── LICENSE
└── .gitignore
```

## Archivo `.gitignore` recomendado

```gitignore
# Entornos virtuales
.venv/
venv/

# Python
__pycache__/
*.py[cod]

# Herramientas y editores
.vscode/
.idea/

# Sistema operativo
.DS_Store
Thumbs.db

# Archivos EPUB generados para pruebas
output/
```

No añadas `*.epub` al archivo `.gitignore` si quieres incluir EPUB de ejemplo en el repositorio. Asegúrate de que tienes permiso para publicar cualquier libro de prueba.

## Creación de un ejecutable opcional

Puedes generar un ejecutable con PyInstaller:

```bash
python -m pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name "EPUB-Page-Break-Generator" epub_paginador_gui.py
```

El resultado se guardará en la carpeta `dist`.

> La creación del ejecutable es opcional. Conviene probarlo en el mismo sistema operativo en el que se distribuirá.

## Solución de problemas

### `pip` no se reconoce como comando

Utiliza `pip` a través de Python:

```powershell
py -m pip install -r requirements.txt
```

### No se encuentra `customtkinter`

Instálalo en el mismo entorno desde el que ejecutas la aplicación:

```bash
python -m pip install customtkinter
```

### Error al activar el entorno virtual en PowerShell

Puedes permitir la ejecución únicamente para la sesión actual:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### El resultado tiene demasiadas o muy pocas páginas

Modifica el valor de caracteres por página. Un valor menor genera más páginas y un valor mayor genera menos páginas.

### Un EPUB no se puede procesar

Comprueba que:

- El archivo se abre correctamente en otro lector.
- No está protegido con gestión de derechos digitales.
- Su estructura interna contiene `META-INF/container.xml` y un paquete OPF válido.
- Los documentos XML y XHTML no están dañados.

## Aviso importante

Antes de procesar un libro, conserva una copia del archivo original. Aunque la aplicación genera un archivo nuevo, es recomendable verificar el resultado en varios lectores EPUB.

Utiliza únicamente archivos para los que tengas los permisos necesarios. Este proyecto no elimina protecciones ni sistemas de gestión de derechos digitales.

## Contribuciones

Las mejoras y correcciones son bienvenidas:

1. Crea un _fork_ del repositorio.
2. Crea una rama para tu cambio:

   ```bash
   git checkout -b mejora/nombre-del-cambio
   ```

3. Guarda tus cambios con un mensaje descriptivo.
4. Sube la rama a tu repositorio.
5. Abre una _pull request_.

## Autor

Desarrollado por **Ernest Anguera Aixala**.

## Licencia

Este repositorio todavía no especifica una licencia.

Antes de publicarlo, añade un archivo `LICENSE`. Si quieres que otras personas puedan utilizar, modificar y distribuir el proyecto de forma sencilla, puedes valorar una licencia permisiva como MIT. La elección de la licencia depende de cómo quieras compartir el código.
