import tkinter as tk
from tkinter import ttk, messagebox, CENTER, filedialog

from ui.table_view import Tableview

class ConfirmationWindowLPWGS(tk.Toplevel):
    """Окно подтверждения для нецелевого образца в режиме LPWGS (технический документ 10x, без выгрузки в БД)."""

    def __init__(self, master, sample: str):
        super().__init__(master)
        self.clinreport = self.master.clinreport
        self.sample = sample
        self.title(f"Образец {self.sample} (LPWGS)")
        self.geometry("850x650")
        self.style = ttk.Style(self)
        self.style.configure('Treeview', rowheight=40)

        self.actions_frame = ttk.Frame(self)
        self.actions_frame.pack(pady=8)

        self.save_button = tk.Button(self.actions_frame, text="Сохранить как ...", command=self.save_docx_lpwgs)
        self.save_button.pack(side="left", padx=6)

        self.close_button = tk.Button(self.actions_frame, text="Закрыть", command=self.close)
        self.close_button.pack(side="left", padx=6)

        self.container = ttk.Frame(self)
        self.container.pack(fill='both', expand=True)

        self.canvas = tk.Canvas(self.container)
        self.canvas.pack(side='left', fill='both', expand=True)

        self.scrollbar = ttk.Scrollbar(self.container, orient='vertical', command=self.canvas.yview)
        self.scrollbar.pack(side='right', fill='y')

        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor='nw')

        self.pack_tableviews_lpwgs()

        self.bind_mousewheel_recursively(self.scrollable_frame)

    def bind_mousewheel_recursively(self, widget):
        widget.bind("<MouseWheel>", self._on_mousewheel)
        for child in widget.winfo_children():
            self.bind_mousewheel_recursively(child)

    def _on_mousewheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(int(-1 * (event.delta)), "units")

    def pack_tableviews_lpwgs(self) -> None:
        # 10x case header (display labels -> data keys)
        self.case_header_map = {
            'Лабораторный номер': 'Номер образца',
            'Пол': 'Пол пациента',
            'Направительный диагноз ребенка': 'Предварительный диагноз',
        }
        common_columns = list(self.case_header_map.keys())
        common_values = [[self.clinreport.data[self.sample][self.case_header_map[col]] for col in common_columns]]
        container = ttk.Frame(self.scrollable_frame)
        container.pack(fill='x', pady=5, padx=10)
        self.common_columns = common_columns
        self.common_tableview = Tableview(container, columns=common_columns, show="headings")
        for col in common_columns:
            self.common_tableview.heading(col, text=col)
            self.common_tableview.column(col, width=100, anchor='w')
        for row in common_values:
            self.common_tableview.insert("", tk.END, values=row)
        self.common_tableview.pack(side='left', fill='x', expand=True)

        self.lpwgs_columns = list(self.clinreport.main_table_header_10x)
        self.lpwgs_rows = self.clinreport.get_lpwgs_table_data(self.sample)
        lpwgs_values = [[r[col] for col in self.lpwgs_columns] for r in self.lpwgs_rows]
        lp_frame = ttk.Frame(self.scrollable_frame)
        lp_frame.pack(pady=10, padx=10, fill="both", expand=True)
        self.lpwgs_tableview = Tableview(lp_frame, columns=self.lpwgs_columns, show="headings")
        for col in self.lpwgs_columns:
            self.lpwgs_tableview.heading(col, text=col)
            self.lpwgs_tableview.column(col, width=120, anchor='w')
        for row in lpwgs_values:
            self.lpwgs_tableview.insert("", tk.END, values=row)
        self.lpwgs_tableview.config(height=len(lpwgs_values) + 3 if lpwgs_values else 0)
        self.lpwgs_tableview.pack(side='left', fill='both', expand=True)

    def get_tableview_changes(self, tableview) -> list:
        tableview_changes = []
        for item in tableview.get_children():
            values = tableview.item(item, 'values')
            tableview_changes.append(dict(zip(tableview['columns'], values)))
        return tableview_changes

    def save_tableviews_changes_lpwgs(self) -> None:
        if hasattr(self, "common_tableview"):
            common_changes = self.get_tableview_changes(self.common_tableview)
            if common_changes:
                for display_key, value in common_changes[0].items():
                    data_key = self.case_header_map.get(display_key, display_key)
                    self.clinreport.data[self.sample][data_key] = value
        if hasattr(self, "lpwgs_tableview"):
            self.lpwgs_rows = self.get_tableview_changes(self.lpwgs_tableview)

    def save_docx_lpwgs(self) -> None:
        self.save_tableviews_changes_lpwgs()
        self.doc = self.clinreport.create_doc_lpwgs(self.sample, lpwgs_variants=getattr(self, "lpwgs_rows", None))
        self.lift()
        try:
            self.attributes("-topmost", True)
            self.update_idletasks()
        except Exception:
            pass
        filepath = filedialog.asksaveasfilename(
            parent=self,
            title='Сохранить как ...',
            defaultextension=".docx",
            filetypes=[("DOCX files", "*.docx")],
            initialfile=f'Заключение LPWGS ({str(self.sample).split(".")[0]}).docx'
        )
        try:
            self.attributes("-topmost", False)
        except Exception:
            pass
        if filepath:
            try:
                self.doc.save(filepath)
                messagebox.showinfo("Успешно", "Документ сохранен", parent=self)
            except Exception as e:
                messagebox.showerror("Ошибка", f"Ошибка при сохранении документа: {repr(e)}", parent=self)

    def close(self) -> None:
        self.destroy()