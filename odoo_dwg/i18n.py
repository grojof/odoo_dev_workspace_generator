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
}

# Runtime lookup: English (the in-code source) → Spanish.
_ES: dict[str, str] = {english: spanish for spanish, english in _ES_TO_EN.items()}
