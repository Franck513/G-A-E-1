import json
import os
from datetime import datetime
from pathlib import Path
import tempfile
import flet as ft

# Imports des vues
from views.agenda import AgendaView
from views.articles import ArticlesView
from views.clients import ClientsView
from views.comptabilite import ComptabiliteView
from views.create_document import CreateDocumentView
from views.dashboard import DashboardView
from views.entreprise import EntrepriseView
from views.facturation import FacturationView
from views.finance import FinanceView
from views.fournisseurs import FournisseursView
from views.mails import MailsView
from views.pdfviewer import PDFViewer
from views.reglages import ReglagesView


def get_config_file_path(page: ft.Page = None) -> Path:
    """Retourne l'emplacement du fichier de configuration interne."""
    if page and getattr(page, "app_storage_dir", None):
        return Path(page.app_storage_dir) / ".facturation_app_config.json"
    return Path.home() / ".facturation_app_config.json"


def get_default_database_path(page: ft.Page = None) -> Path:
    """Détermine le chemin d'accès sécurisé pour la base Android (ou PC)."""
    if page and getattr(page, "app_storage_dir", None):
        base = Path(page.app_storage_dir)
    else:
        try:
            base = Path.home() / "facturation_data"
            base.mkdir(parents=True, exist_ok=True)
        except Exception:
            base = Path(tempfile.gettempdir()) / "facturation_data"

    base.mkdir(parents=True, exist_ok=True)
    return base / "database.json"


def load_saved_db_path(page: ft.Page = None) -> Path:
    """Lit le chemin de la base configurée ou bascule sur le stockage privé."""
    cfg_file = get_config_file_path(page)
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                custom = cfg.get("database_path")
                if custom and Path(custom).parent.exists():
                    return Path(custom)
        except Exception:
            pass
    return get_default_database_path(page)


def save_config_db_path(db_path: Path, page: ft.Page = None):
    """Enregistre le chemin dans la configuration."""
    cfg_file = get_config_file_path(page)
    try:
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump({"database_path": str(db_path)}, f, indent=4)
    except Exception as e:
        print("Erreur écriture config :", e)


def sanitize_for_json(obj):
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [sanitize_for_json(i) for i in obj]
    if isinstance(obj, (Path, datetime)):
        return str(obj)
    return obj


class FacturationAndroidApp:

    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "Gestion Auto Entreprise par Francky"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0
        self.page.scroll = None

        # Base de données sur espace de stockage sécurisé Android
        self.database = load_saved_db_path(self.page)

        self.file_picker = None

        self.devis = []
        self.factures = []
        self.clients = []
        self.articles = []
        self.fournisseurs = []
        self.mails = []
        self.bons_commande = []
        self.bons_livraison = []
        self.agenda = {}

        self.entreprise = {
            "nom": "MA GESTION",
            "statut_juridique": "Micro-Entreprise",
            "adresse": "",
            "telephone": "",
            "email": "",
            "site": "",
            "siret": "",
            "tva_activee": False,
            "accent_color": "#2B719E",
        }

        self.load_data()

        self.content_area = ft.Container(expand=True, padding=10)
        self.setup_layout()
        self.page.on_resized = self.on_responsive_resize
        self.navigate_to("Dashboard")

    def _get_file_picker(self):
        """Initialise le FilePicker à la demande pour éviter tout crash au démarrage."""
        if self.file_picker is None:
            try:
                picker = ft.FilePicker()
                picker.on_result = self._on_file_picker_result
                self.page.overlay.append(picker)
                self.page.update()
                self.file_picker = picker
            except Exception as ex:
                print("FilePicker non supporté par cet APK :", ex)
                return None
        return self.file_picker

    def exporter_sauvegarde(self):
        """Ouvre le sélecteur Android pour sauvegarder la BDD (si supporté)."""
        picker = self._get_file_picker()
        if picker:
            try:
                picker.save_file(
                    dialog_title="Enregistrer la sauvegarde",
                    file_name="backup_database.json",
                    allowed_extensions=["json"],
                )
            except Exception as ex:
                self.show_snack(f"Export non supporté sur ce build : {ex}", is_error=True)
        else:
            self.show_snack("Le sélecteur de fichiers n'est pas inclus dans cet APK.", is_error=True)

    def importer_sauvegarde(self):
        """Ouvre le sélecteur Android pour charger un fichier (si supporté)."""
        picker = self._get_file_picker()
        if picker:
            try:
                picker.pick_files(
                    dialog_title="Sélectionner une sauvegarde JSON",
                    allowed_extensions=["json"],
                    allow_multiple=False,
                )
            except Exception as ex:
                self.show_snack(f"Import non supporté sur ce build : {ex}", is_error=True)
        else:
            self.show_snack("Le sélecteur de fichiers n'est pas inclus dans cet APK.", is_error=True)

    def _on_file_picker_result(self, e: ft.FilePickerResultEvent):
        if e.path:
            try:
                import shutil
                shutil.copy(self.database, e.path)
                self.show_snack(f"Sauvegarde exportée sous : {e.path}")
            except Exception as ex:
                self.show_snack(f"Erreur lors de la sauvegarde : {ex}", is_error=True)

        elif e.files and len(e.files) > 0:
            imported_file = e.files[0].path
            if imported_file and os.path.exists(imported_file):
                try:
                    import shutil
                    shutil.copy(imported_file, self.database)
                    self.load_data()
                    self.navigate_to("Dashboard")
                    self.show_snack("Base de données restaurée avec succès !")
                except Exception as ex:
                    self.show_snack(f"Erreur de restauration : {ex}", is_error=True)

    def show_snack(self, message: str, is_error: bool = False):
        snack = ft.SnackBar(
            content=ft.Text(message),
            bgcolor="#B91C1C" if is_error else "#15803D",
        )
        try:
            self.page.open(snack)
        except Exception:
            self.page.snack_bar = snack
            snack.open = True
            self.page.update()

    def load_data(self):
        if not self.database.exists():
            self.save_data()
            return
        try:
            with open(self.database, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.devis = data.get("devis", [])
            self.factures = data.get("factures", [])
            self.clients = data.get("clients", [])
            self.articles = data.get("articles", [])
            self.fournisseurs = data.get("fournisseurs", [])
            self.mails = data.get("mails", [])
            self.bons_commande = data.get("bons_commande", [])
            self.bons_livraison = data.get("bons_livraison", [])
            self.agenda = data.get("agenda", {})

            entreprise = data.get("entreprise")
            if isinstance(entreprise, dict):
                self.entreprise.update(entreprise)
        except Exception as e:
            print("Erreur chargement :", e)

    def save_data(self):
        package = {
            "devis": self.devis,
            "factures": self.factures,
            "clients": self.clients,
            "articles": self.articles,
            "fournisseurs": self.fournisseurs,
            "mails": self.mails,
            "bons_commande": self.bons_commande,
            "bons_livraison": self.bons_livraison,
            "agenda": self.agenda,
            "entreprise": self.entreprise,
        }
        try:
            self.database.parent.mkdir(parents=True, exist_ok=True)
            with open(self.database, "w", encoding="utf-8") as f:
                json.dump(sanitize_for_json(package), f, indent=4, ensure_ascii=False)
        except Exception as e:
            print("Erreur sauvegarde :", e)

    def setup_layout(self):
        nom_entreprise = self.entreprise.get("nom", "GESTION")

        self.menu_button = ft.Container(
            content=ft.Text("☰", size=24, color="white"),
            padding=10,
            on_click=self.toggle_mobile_menu,
            ink=True,
        )

        self.top_bar_title = ft.Text(nom_entreprise, size=18, weight=ft.FontWeight.BOLD, color="white")

        self.top_bar = ft.Container(
            height=56,
            bgcolor="#1A1A1C",
            padding=5,
            content=ft.Row([self.menu_button, self.top_bar_title], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            visible=False,
        )

        self.mobile_menu_column = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO)
        self.mobile_menu = ft.Container(bgcolor="#222225", padding=10, visible=False, content=self.mobile_menu_column)

        self.sidebar_titre = ft.Text(nom_entreprise, size=22, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)

        self.menu_column = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll=ft.ScrollMode.AUTO, expand=True)

        btn_reglages = ft.OutlinedButton("⚙️ Réglages", width=220, height=45, on_click=lambda e: self.navigate_to("Réglages"))

        self.sidebar = ft.Container(
            width=250,
            bgcolor="#1A1A1C",
            padding=10,
            content=ft.Column(
                controls=[
                    ft.Container(content=self.sidebar_titre, padding=20),
                    ft.Divider(),
                    self.menu_column,
                    ft.Divider(),
                    btn_reglages,
                ],
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            ),
        )

        self.page.add(
            ft.Column(
                controls=[
                    self.top_bar,
                    self.mobile_menu,
                    ft.Row(controls=[self.sidebar, self.content_area], expand=True, spacing=0),
                ],
                expand=True,
                spacing=0,
            )
        )

        self.refresh_sidebar()
        self.on_responsive_resize()

    def toggle_mobile_menu(self, e=None):
        self.mobile_menu.visible = not self.mobile_menu.visible
        self.page.update()

    def on_responsive_resize(self, e=None):
        width = self.page.width if (self.page.width and self.page.width > 0) else 360
        is_mobile = width < 768

        self.sidebar.visible = not is_mobile
        self.top_bar.visible = is_mobile

        if not is_mobile:
            self.mobile_menu.visible = False

        try:
            self.page.update()
        except Exception:
            pass

    def refresh_sidebar(self):
        accent = self.entreprise.get("accent_color", "#2B719E")
        nom_ent = self.entreprise.get("nom", "GESTION").upper()

        self.sidebar_titre.value = nom_ent
        if self.top_bar_title:
            self.top_bar_title.value = nom_ent

        menu = [
            ("📊 Dashboard", "Dashboard"),
            ("🧾 Facturation", "Facturation"),
            ("📦 Articles", "Articles"),
            ("👥 Clients", "Clients"),
            ("🚚 Fournisseurs", "Fournisseurs"),
            ("📚 Visionneuse PDF", "PDFViewer"),
            ("📈 Finance", "Finance"),
        ]

        if self.entreprise.get("tva_activee", False):
            menu.append(("🧮 Comptabilité", "Comptabilite"))

        menu.extend([
            ("✉️ Mails", "Mails"),
            ("📅 Agenda", "Agenda"),
            ("🏢 Entreprise", "Entreprise"),
        ])

        self.menu_buttons = []
        for texte, vue in menu:
            btn = ft.ElevatedButton(
                texte,
                width=220,
                height=45,
                bgcolor=accent,
                color="white",
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                on_click=lambda e, v=vue: self.navigate_to(v),
            )
            self.menu_buttons.append(btn)

        self.menu_column.controls = self.menu_buttons

        mobile_controls = []
        for texte, vue in menu:
            def make_click(v):
                return lambda e: self.navigate_to(v)

            mobile_controls.append(
                ft.ElevatedButton(
                    texte,
                    height=42,
                    bgcolor=accent,
                    color="white",
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
                    on_click=make_click(vue),
                )
            )

        mobile_controls.append(
            ft.OutlinedButton("⚙️ Réglages", height=42, on_click=lambda e: self.navigate_to("Réglages"))
        )

        self.mobile_menu_column.controls = mobile_controls

        try:
            self.menu_column.update()
            self.mobile_menu_column.update()
        except Exception:
            pass

    def navigate_to(self, view_name, **kwargs):
        if self.mobile_menu.visible:
            self.mobile_menu.visible = False

        self.refresh_sidebar()
        self.content_area.content = None

        try:
            views_map = {
                "Dashboard": lambda: DashboardView(self),
                "Facturation": lambda: FacturationView(self),
                "Articles": lambda: ArticlesView(self),
                "Clients": lambda: ClientsView(self),
                "Fournisseurs": lambda: FournisseursView(self),
                "Finance": lambda: FinanceView(self),
                "Comptabilite": lambda: ComptabiliteView(self),
                "Agenda": lambda: AgendaView(self),
                "Entreprise": lambda: EntrepriseView(self),
                "Mails": lambda: MailsView(self),
                "PDFViewer": lambda: PDFViewer(self, **kwargs),
                "Réglages": lambda: ReglagesView(self),
                "create_document": lambda: CreateDocumentView(
                    self,
                    doc_type=kwargs.get("doc_type", "devis"),
                    doc_to_edit=kwargs.get("doc_to_edit", None),
                ),
                "NouveauDevis": lambda: CreateDocumentView(self, doc_type="devis"),
                "NouvelleFacture": lambda: CreateDocumentView(self, doc_type="facture"),
                "NouveauBonCommande": lambda: CreateDocumentView(self, doc_type="bon_commande"),
                "NouveauBonLivraison": lambda: CreateDocumentView(self, doc_type="bon_livraison"),
            }

            if view_name in views_map:
                self.content_area.content = views_map[view_name]()
            else:
                self.content_area.content = ft.Text(f"Vue '{view_name}' introuvable.")
        except Exception as e:
            self.content_area.content = ft.Text(f"Erreur : {e}", color="red")

        self.page.update()


def main(page: ft.Page):
    FacturationAndroidApp(page)


if __name__ == "__main__":
    ft.app(target=main)
