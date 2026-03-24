import tkinter as tk
from tkinter import ttk, messagebox
import json


class SettingsWindow(tk.Toplevel):
    """Окно настроек."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Настройки")
        self.geometry("420x350")  # Установите желаемый размер

        self.labels, self.entries, self.switches = {}, {}, {}
        
        for row, (key, value) in enumerate(self.master.config.items()):
            if key == 'auto_upload':
                self.auto_upload_var = tk.BooleanVar(value=self.master.config.get('auto_upload', True))
                self.switches['auto_upload'] = ttk.Checkbutton(
                    self,
                    text="Автоматически выгружать в БД при сохранении",
                    variable=self.auto_upload_var
                )
                self.switches['auto_upload'].grid(row=row, column=0, columnspan=2, padx=5, pady=10, sticky=tk.W)
            else:
                self.labels[key] = ttk.Label(self, text=f"{key}:")
                self.labels[key].grid(row=row, column=0, padx=5, pady=5, sticky=tk.W)
                self.entries[key] = ttk.Entry(self)
                self.entries[key].insert(0, str(value))  # Преобразуем значение в строку
                self.entries[key].grid(row=row, column=1, padx=5, pady=5, sticky=tk.EW)

        
        self.save_button = tk.Button(self, text="Сохранить", command=self.save_settings)
        self.save_button.grid(row=len(self.entries)+1, column=0, columnspan=2, padx=5, pady=10)


    def save_settings(self):
        """Сохраняет настройки в json."""
        for key, entry in self.entries.items():
            self.master.config[key] = entry.get()

        self.master.config['auto_upload'] = self.auto_upload_var.get()

        try:
            with open(self.master.config_path, 'w') as f:
                json.dump(self.master.config, f)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при сохранении настроек: {repr(e)}")