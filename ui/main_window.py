import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import traceback
import shutil

from utils import load_config, get_ru_annotations
from clinreport import ClinReport
from database import Database

from ui.settings_window import SettingsWindow
from ui.confirmation_window_lpwgs import ConfirmationWindowLPWGS
from ui.confirmation_window import ConfirmationWindow
from ui.processing_window import ProcessingWindow


class MainWindow(tk.Tk):
    """Главное окно приложения."""

    def __init__(self):
        super().__init__()
        self.title("ClinReport v2.1")
        self.geometry("400x200")  # Установите желаемый размер

        self.select_file_button = tk.Button(self, text="Выбрать файл", command=self.select_file)
        self.select_file_button.pack(pady=20)

        self.settings_button = tk.Button(self, text="Настройки", command=self.open_settings)
        self.settings_button.pack(pady=20)

        self.config_path = self.get_config_path('config.json')
        self.config = load_config(self.config_path)
        self.config = load_config(self.config_path)

        if 'auto_upload' not in self.config:
            self.config['auto_upload'] = True

        self.clinreport = None
        self.ru_annotations = self.setup_ru_annotations()
        self.setup_database()

    def setup_styles(self):
        """Настройка стилей для Treeview (темный текст на светлом фоне) с дефолтными настройками остального"""
        style = ttk.Style(self)
        
        # Сбросить все стили к стандартным (тема 'default' или 'clam')
        style.theme_use('clam')  # 'clam' — более современная тема с лучшей поддержкой цветов
        
        # Настройка Treeview: светлый фон + темный текст
        style.configure("Treeview",
            background="white",      # Светлый фон
            foreground="black",     # Темный текст
            fieldbackground="white", # Фон ячеек
            rowheight=25,           # Высота строки
            font=('Helvetica', 10)  # Шрифт
        )

    def get_config_path(self, config_fname):
        """Путь к файлу настроек рядом с exe."""
        app_dir = self.get_app_dir()
        config_path = os.path.join(app_dir, config_fname)
        try:
            self.ensure_config_exists(config_path, config_fname)
        except:
            messagebox.showwarning("Проблема конфигурации", f"{traceback.format_exc()}")
        return config_path


    def get_app_dir(self):
        """Возвращает папку, где лежит исполняемый файл или скрипт."""
        if getattr(sys, 'frozen', False):
            # Запуск из PyInstaller exe
            return os.path.dirname(sys.executable)
        else:
            # Запуск из скрипта
            return os.path.dirname(os.path.abspath(__file__))


    def ensure_config_exists(self, config_path, config_fname):
        if not os.path.exists(config_path):
            # Копируем дефолтный конфиг из ресурсов
            default_config_path = self.get_default_config_path(config_fname)
            shutil.copyfile(default_config_path, config_path)


    def get_default_config_path(self, config_fname):
        """Путь к дефолтному конфигу внутри пакета PyInstaller."""
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, config_fname)


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


    def process_file(self, filepath, target_sample):
        """Обрабатывает файл в зависимости от выбранного типа."""
        try:
            clinician = self.config.get('clinician', '')
            self.clinreport = ClinReport(filepath, clinician=clinician, ru_annotations=self.ru_annotations)
            self.clinreport.get_data()
            self.clinreport.target_sample = target_sample
            for sample in self.clinreport.all_samples:
                    ConfirmationWindow(self, sample)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при обработке файла: {traceback.format_exc()}")

    def process_file_lpwgs(self, filepath, target_sample):
        """Обрабатывает файл в режиме LPWGS: целевой — стандартный отчёт, нецелевые — технический документ 10x."""
        try:
            clinician = self.config.get('clinician', '')
            self.clinreport = ClinReport(filepath, clinician=clinician, ru_annotations=self.ru_annotations)
            self.clinreport.get_data()
            # Quick fix. From dropdown menu we get str but clinreport.py may use None if sample doesn't have a name
            target_sample = self.clinreport.target_sample if self.clinreport.target_sample != "None" else None
            ConfirmationWindow(self, target_sample, lpwgs_target=True)
            for sample in self.clinreport.all_samples:
                if sample != target_sample:
                    # Just in case
                    sample = sample if sample != "None" else None
                    ConfirmationWindowLPWGS(self, sample)
        except Exception as e:
            messagebox.showerror(   "Ошибка", f"Ошибка при обработке файла: {traceback.format_exc()}")
