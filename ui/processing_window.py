import tkinter as tk
from tkinter import ttk
from pathlib import Path

from clinreport import ClinReport

class ProcessingWindow(tk.Toplevel):
    """Окно выбора обработки."""

    def __init__(self, master, filepath, process_file_callback, process_file_lpwgs_callback):
        super().__init__(master)
        self.filepath = filepath
        self.process_file_callback = process_file_callback
        self.process_file_lpwgs_callback = process_file_lpwgs_callback
        self.title(f"{Path(filepath).name}")
        self.geometry("300x200")  # Button isn't visible if 300x150

        self.text = tk.Label(self, text="Целевой образец:")
        self.text.pack(pady=10)

        self.clinreport = ClinReport(filepath)

        self.target_sample = ttk.Combobox(self, values=self.clinreport.all_samples, width=30, state='readonly')
        self.target_sample.current(0)
        self.target_sample.pack(pady=10)

        self.confirm_button = tk.Button(self, text="Обработать", command=self.confirm_selection)
        self.confirm_button.pack(pady=5)

        self.confirm_lpwgs_button = tk.Button(self, text="Обработать как LPWGS", command=self.confirm_selection_lpwgs)
        self.confirm_lpwgs_button.pack(pady=(0, 10))


    def confirm_selection(self):
        """Подтверждает выбор типа обработки и вызывает callback."""
        selected_type = self.target_sample.get()
        self.process_file_callback(self.filepath, selected_type)  # Передаем имя файла и выбранный тип
        self.destroy()

    def confirm_selection_lpwgs(self):
        """Подтверждает выбор и вызывает LPWGS callback."""
        selected_type = self.target_sample.get()
        self.process_file_lpwgs_callback(self.filepath, selected_type)
        self.destroy()