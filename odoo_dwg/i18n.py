"""Lightweight, modular UI translation (mirrors ``odoo_instance_manager``).

English is the source language: the string in the code is already English, so the
default UI needs no translation. When Spanish is selected, translation happens at
a few display/input chokepoints (see ``ui``/``prompts``) plus ``tf`` for
interpolated messages, so call sites barely change. Any string missing from the
catalog falls back to English, so partial translation degrades gracefully.

The authoring catalog below is kept Spanish→English (one readable source of
truth); the English→Spanish lookup table used at runtime is derived from it.
"""

from __future__ import annotations

_LANG = "en"


def set_language(lang: str) -> None:
    global _LANG
    _LANG = "es" if str(lang).lower().startswith("es") else "en"


def current_language() -> str:
    return _LANG


def t(text: str) -> str:
    """Translate an English UI string to the current language (English → Spanish)."""
    if _LANG == "en":
        return text
    return _ES.get(text, text)


def tf(template: str, *args: object, **kwargs: object) -> str:
    """Translate a message template, then fill its ``{}``/``{name}`` placeholders.

    The English template is the catalog key, so interpolated messages translate
    too — e.g. ``tf("Already exists {}", path)`` looks up ``"Already exists {}"``.
    """
    return t(template).format(*args, **kwargs)


# Authoring catalog (Spanish source → English). Extend by adding entries here;
# ``_ES`` (the runtime English → Spanish table) is derived from it below.
_ES_TO_EN: dict[str, str] = {
    # startup / top-level menu
    "Idioma / Language": "Idioma / Language",
    "Generador de workspaces de desarrollo y migración de Odoo": "Odoo development & migration workspace generator",
    "- Genera y mantiene workspaces de Odoo Community por cliente": "- Generates and maintains per-client Odoo Community workspaces",
    "- Secciones opcionales: provisión del sistema y migración (12→19)": "- Optional sections: system provisioning and migration (12→19)",
    "- Muestra el plan de comandos antes de ejecutar nada": "- Shows the command plan before running anything",
    "\n¿Qué quieres hacer?": "\nWhat do you want to do?",
    "Workspaces (generar / gestionar)": "Workspaces (create / manage)",
    "Provisión del sistema (opcional)": "System provisioning (optional)",
    "Migración (OpenUpgrade 12→19)": "Migration (OpenUpgrade 12→19)",
    "Salir": "Exit",
    "\nSaliendo.": "\nExiting.",
    "\nOperación interrumpida. Volviendo al menú.": "\nOperation interrupted. Returning to the menu.",
    "\nEntrada cerrada. Saliendo.": "\nInput closed. Exiting.",
    "\n[ERROR] La operación no se completó: {}": "\n[ERROR] The operation did not complete: {}",
    "(aún no implementado)": "(not implemented yet)",
    # generic menu chrome
    "Volver": "Back",
    "Cancelar": "Cancel",
    "Selecciona opción": "Select an option",
    "Introduce el número de opción.": "Enter the option number.",
    "Opción fuera de rango.": "Option out of range.",
    "Sin selección (0 para cancelar).": "No selection (0 to cancel).",
    "Confirmar acción": "Confirm action",
    "Plan de ejecución": "Execution plan",
    "Comando terminó con código {}.": "Command finished with code {}.",
    # prompt primitives
    "Valor obligatorio.": "Value is required.",
    "Debe ser un número entero.": "Must be an integer.",
    "Valor fuera de rango ({}-{}).": "Value out of range ({}-{}).",
    "Responde 'sí'/'s' o 'no'/'n' (Enter = opción por defecto).": "Answer 'yes'/'y' or 'no'/'n' (Enter = default).",
    "Escribe exactamente": "Type exactly",
    "para confirmar": "to confirm",
    # apply / safety
    "Para aplicar cambios en el sistema ejecuta con privilegios (sudo).": "To apply system changes, run with privileges (sudo).",
    "Fallo ejecutando: ": "Failed running: ",
    # migration
    "Generar un entorno de migración": "Generate a migration environment",
    "Limpiar un entorno de migración": "Clean a migration environment",
    "Qué entorno": "Which environment",
    "No hay entornos de migración en {}.": "No migration environments found under {}.",
    "¿Eliminar también la caché compartida de clones (.repos)? La usan todos los entornos de migración.": "Also remove the shared clones cache (.repos)? It serves every migration environment.",
    "Esto elimina permanentemente {}.": "This permanently deletes {}.",
    "Cancelado.": "Cancelled.",
    "Entorno de migración eliminado.": "Migration environment removed.",
    "La base de datos PostgreSQL de migración (si existe) no se toca — bórrala con dropdb cuando quieras una ejecución totalmente limpia.": "The PostgreSQL migration database (if any) is untouched — drop it with dropdb when you want a fully clean run.",
    "Elimina el entorno de migración {}": "Remove migration environment {}",
    "Elimina la caché compartida de clones {}": "Remove shared migration clones {}",
    # preflight
    "Comprobación previa (preflight)": "Preflight check",
    "Fichero de dump origen a verificar (vacío para omitir)": "Source dump file to verify (empty to skip)",
    "Base de datos existente a verificar (vacío para omitir)": "Existing database to verify (empty to skip)",
    "Faltan comprobaciones requeridas (MISSING) — ¿continuar de todos modos?": "Some required checks are MISSING — continue anyway?",
    "Resuelve las comprobaciones MISSING antes de ejecutar la migración.": "Resolve the MISSING checks before running the migration.",
    "Preflight superado.": "Preflight passed.",
    "¿Instalar Docker Engine? (solo necesario para los pasos de migración de Odoo 12/13)": "Install Docker Engine? (only needed for Odoo 12/13 migration steps)",
    "¿Descargar las imágenes de reserva de OpenUpgrade (odoo:13.0, odoo:12.0)?": "Pull the OpenUpgrade fallback images (odoo:13.0, odoo:12.0)?",
    "Instala Docker Engine (docker.io)": "Install Docker Engine (docker.io)",
    "Habilita y arranca el servicio Docker": "Enable and start the Docker service",
    "Descarga la imagen Docker {}": "Pull Docker image {}",
    # staging
    "Preparar módulos custom (staging)": "Stage custom modules",
    "La herramienta de staging (odoo-module-migrator) no está instalada. Este plan la instala:": "The staging tool (odoo-module-migrator) is not installed. This plan installs it:",
    "Directorio con tus módulos custom (en la versión origen)": "Directory containing your custom modules (at the source version)",
    "Módulos a preparar (separados por comas, vacío = todos)": "Modules to stage (comma-separated, empty = all)",
    "No es un directorio: {}": "Not a directory: {}",
    "No encontrados en el directorio origen: {}": "Not found in the source directory: {}",
    "No hay módulos que preparar.": "No modules to stage.",
    "Sin clon de OpenUpgrade para {} — la detección de candidatos quedará vacía en esos pasos (genera antes el entorno).": "No OpenUpgrade clone for {} — candidate detection will be empty for those steps (generate the environment first).",
    "Esto reemplaza el código ya preparado de: {}.": "This replaces the already-staged code of: {}.",
    "Informe de staging: {}": "Staging report: {}",
    "El staging es un punto de partida preparado — tu revisión completa la migración.": "Staging is a prepared starting point — your review completes the migration.",
}

# Runtime lookup: English (the in-code source) → Spanish.
_ES: dict[str, str] = {english: spanish for spanish, english in _ES_TO_EN.items()}
