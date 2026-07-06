import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import traceback

import config
from clinreport import ClinReport
from database import Database, get_ru_annotations

from ui.settings_window import SettingsWindow
from ui.confirmation_window_lpwgs import ConfirmationWindowLPWGS
from ui.confirmation_window import ConfirmationWindow
from ui.processing_window import ProcessingWindow


class MainWindow(tk.Tk):
    """Главное окно приложения."""

    def __init__(self):
        super().__init__()
        self.title("ClinReport v2.2 (beta)")
        self.geometry("400x200")  # Установите желаемый размер

        self.select_file_button = tk.Button(self, text="Выбрать файл", command=self.select_file)
        self.select_file_button.pack(pady=20)

        self.settings_button = tk.Button(self, text="Настройки", command=self.open_settings)
        self.settings_button.pack(pady=20)

        try:
            self.config_path = config.get_config_path()
        except Exception:
            messagebox.showwarning("Проблема конфигурации", f"{traceback.format_exc()}")
            self.config_path = config.get_app_dir() + '/' + config.CONFIG_FILENAME
        self.config = config.load_config(self.config_path)

        if 'auto_upload' not in self.config:
            self.config['auto_upload'] = True

        self.clinreport = None
        self.ru_annotations = self.setup_ru_annotations()
        self.setup_database()

    def setup_database(self):
        self.database = None
        try:
            self.database = Database(db_creds=self.config)
        except Exception as e:
            messagebox.showwarning("Проблема с подключением к БД", f"{traceback.format_exc()}")


    def setup_ru_annotations(self):
        try:
            return get_ru_annotations()
        except Exception as e:
            messagebox.showwarning('Летмиспикфромахарт', f"Проблема с получением аннотаций на русском: {repr(e)}")
        

    def select_file(self):
        """Открывает диалоговое окно выбора файла."""
        filepath = filedialog.askopenfilename(filetypes=[("SQLite files", "*.sqlite"), ("All files", "*.*")])
        if filepath:
            self.open_processing_window(filepath)


    def open_settings(self):
        """Открывает окно настроек."""
        SettingsWindow(self)


    def open_processing_window(self, filepath):
        """Открывает окно выбора типа обработки."""
        ProcessingWindow(self, filepath, self.process_file, self.process_file_lpwgs)


    def _resolve_sample(self, clinreport, selected):
        """Map a Combobox string back to the actual sample value (e.g. 'None' -> None)."""
        for sample in clinreport.all_samples:
            if str(sample) == selected:
                return sample
        return selected

    def process_file(self, clinreport, target_sample):
        """Стандартная обработка: для каждого образца открывается окно подтверждения."""
        try:
            clinreport.target_sample = self._resolve_sample(clinreport, target_sample)
            self.clinreport = clinreport
            for sample in clinreport.all_samples:
                context = clinreport.build_context(sample, 'default')
                ConfirmationWindow(self, sample, context)
        except Exception:
            messagebox.showerror("Ошибка", f"Ошибка при обработке файла: {traceback.format_exc()}")

    def process_file_lpwgs(self, clinreport, target_sample):
        """Режим LPWGS: целевой образец — стандартный отчёт, нецелевые — технический документ 10x."""
        try:
            target_sample = self._resolve_sample(clinreport, target_sample)
            clinreport.target_sample = target_sample
            self.clinreport = clinreport
            ConfirmationWindow(self, target_sample, clinreport.build_context(target_sample, 'default'))
            for sample in clinreport.all_samples:
                if sample != target_sample:
                    ConfirmationWindowLPWGS(self, sample, clinreport.build_context(sample, '10x'))
        except Exception:
            messagebox.showerror("Ошибка", f"Ошибка при обработке файла: {traceback.format_exc()}")
