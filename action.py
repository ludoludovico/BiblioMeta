# ============================================================
# BiblioMeta — InterfaceAction v1.1
# ============================================================
# Changelog v1.1:
#   - FIX: get_icons importado correctamente desde calibre.gui2
#   - FIX: show_config apunta a BiblioMeta
#   - UPD: Panel de estado incluye contador Wikidata
# ============================================================

from calibre.gui2.actions import InterfaceAction
from calibre.gui2 import error_dialog
from calibre.utils.config import JSONConfig

try:
    from qt.core import (
        QMenu, QDialog, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QGridLayout, QFrame,
        Qt, QFont
    )
except ImportError:
    from PyQt5.Qt import (
        QMenu, QDialog, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QGridLayout, QFrame,
        Qt, QFont
    )


class BiblioMetaAction(InterfaceAction):

    name        = "BiblioMeta"
    action_spec = (
        "BiblioMeta",
        None,
        "Descargar metadatos con BiblioMeta",
        None,
    )
    action_type               = "current"
    dont_add_to               = frozenset()
    dont_remove_from          = frozenset()
    action_add_menu           = True
    action_menu_clone_qaction = "Descargar metadatos"

    def genesis(self):
        # Importación correcta del helper de iconos de Calibre
        try:
            from calibre.gui2 import get_icons as _get_icons
            icon = _get_icons("images/icon.png")
        except Exception:
            icon = self.interface_action_base_widget.style().standardIcon(0)

        self.qaction.setIcon(icon)
        self.qaction.triggered.connect(self.download_metadata)

        self.menu = QMenu(self.gui)
        self._add_menu_item(
            "Descargar metadatos",
            self.download_metadata,
            "Descarga metadatos para los libros seleccionados usando BiblioMeta",
        )
        self.menu.addSeparator()
        self._add_menu_item(
            "Configuración",
            self.show_config,
            "Abre el panel de configuración de BiblioMeta",
        )
        self.menu.addSeparator()
        self._add_menu_item(
            "Estado",
            self.show_stats,
            "Muestra las estadísticas de la última sesión",
        )
        self.qaction.setMenu(self.menu)

    def _add_menu_item(self, label, handler, tooltip=""):
        action = self.menu.addAction(label)
        action.setToolTip(tooltip)
        action.triggered.connect(handler)
        return action

    # ── Acciones ──────────────────────────────────────────────

    def download_metadata(self):
        rows = self.gui.library_view.selectionModel().selectedRows()
        if not rows:
            error_dialog(
                self.gui, "BiblioMeta",
                "Selecciona al menos un libro en la biblioteca.",
                show=True,
            )
            return
        self.gui.iactions["Edit Metadata"].download_metadata(
            ids=None, covers_only=False
        )

    def show_config(self):
        try:
            self.gui.iactions["Preferences"].do_config(
                initial_plugin=("Metadata Sources", "BiblioMeta"),
                close_after_initial=True,
            )
        except Exception as exc:
            error_dialog(
                self.gui, "BiblioMeta",
                "No se pudo abrir la configuración: %s" % exc,
                show=True,
            )

    def show_stats(self):
        prefs  = JSONConfig("metadata_sources/BiblioMeta")
        stats  = prefs.get("stats", {})
        dialog = StatsDialog(self.gui, stats)
        dialog.exec()


# ── Panel de estado ───────────────────────────────────────────

class StatsDialog(QDialog):

    def __init__(self, parent, stats):
        super().__init__(parent)
        self.setWindowTitle("BiblioMeta — Estado de sesión")
        self.setMinimumWidth(380)
        self._build_ui(stats)

    def _build_ui(self, stats):
        layout = QVBoxLayout()
        self.setLayout(layout)

        title = QLabel("BiblioMeta")
        font  = QFont()
        font.setPointSize(14)
        font.setBold(True)
        title.setFont(font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("Última sesión de descarga")
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        grid = QGridLayout()
        grid.setColumnMinimumWidth(0, 220)
        grid.setColumnMinimumWidth(1, 80)

        total     = stats.get("total", 0)
        found     = stats.get("found", 0)
        not_found = stats.get("not_found", 0)
        bne       = stats.get("bne", 0)
        loc       = stats.get("loc", 0)
        ol        = stats.get("ol", 0)
        wd        = stats.get("wd", 0)
        last_run  = stats.get("last_run", "—")
        pct       = int(found / total * 100) if total > 0 else 0

        rows = [
            ("Libros procesados:",          str(total),             False),
            ("  Encontrados:",              "%d  (%d%%)" % (found, pct), False),
            ("  No encontrados:",           str(not_found),         False),
            ("",                            "",                     True),
            ("BNE (español):",              str(bne),               False),
            ("LoC (inglés):",               str(loc),               False),
            ("Open Library (fallback):",    str(ol),                False),
            ("Wikidata (fallback):",        str(wd),                False),
            ("",                            "",                     True),
            ("Última ejecución:",           last_run,               False),
        ]

        for i, (label, value, is_sep) in enumerate(rows):
            if is_sep:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setFrameShadow(QFrame.Sunken)
                grid.addWidget(sep, i, 0, 1, 2)
            else:
                lbl = QLabel(label)
                val = QLabel(value)
                val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if label.startswith("  "):
                    f = QFont()
                    f.setItalic(True)
                    lbl.setFont(f)
                grid.addWidget(lbl, i, 0)
                grid.addWidget(val, i, 1)

        layout.addLayout(grid)

        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line2)

        btn_layout = QHBoxLayout()

        btn_reset = QPushButton("Reiniciar estadísticas")
        btn_reset.clicked.connect(self._reset_stats)
        btn_layout.addWidget(btn_reset)

        btn_close = QPushButton("Cerrar")
        btn_close.setDefault(True)
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _reset_stats(self):
        prefs = JSONConfig("metadata_sources/BiblioMeta")
        prefs["stats"] = {
            "total": 0, "found": 0, "not_found": 0,
            "bne": 0, "loc": 0, "ol": 0, "wd": 0, "last_run": "—",
        }
        self.accept()
