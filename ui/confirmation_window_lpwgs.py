import traceback
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from ui.table_view import Tableview
from ui import labels


class ConfirmationWindowLPWGS(tk.Toplevel):
    """Окно подтверждения для нецелевого образца в режиме LPWGS.

    Технический документ 10x: общая таблица + основная таблица вариантов,
    без выбора шаблона и без выгрузки в БД. Работает с context-словарём
    (build_context(sample, '10x')); документ формируется через render(context, '10x').
    """

    def __init__(self, master, sample, context: dict):
        super().__init__(master)
        self.clinreport = self.master.clinreport
        self.sample = sample
        self.context = context
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

        self.pack_tableviews()
        self.bind_mousewheel_recursively(self.scrollable_frame)

    def bind_mousewheel_recursively(self, widget):
        widget.bind("<MouseWheel>", self._on_mousewheel)
        for child in widget.winfo_children():
            self.bind_mousewheel_recursively(child)

    def _on_mousewheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(int(-1 * event.delta), "units")

    def pack_tableviews(self) -> None:
        common_labels = [label for _, _, label in labels.TEN_X_COMMON_FIELDS]
        common = labels.common_values(self.context, labels.TEN_X_COMMON_FIELDS)
        self.common_tableview = self._pack_table(common_labels, common)

        ttk.Label(self.scrollable_frame, text="Результаты исследования", font=('Helvetica', 10, 'bold')).pack(pady=(10, 0))
        column_labels = [labels.MAIN_VARIANT_LABELS[field] for field in labels.MAIN_VARIANT_FIELDS]
        values = labels.variant_rows_to_values(self.context.get('main_variants', []), labels.MAIN_VARIANT_FIELDS)
        self.main_tableview = self._pack_table(column_labels, values)

    def _pack_table(self, columns, values) -> Tableview:
        frame = ttk.Frame(self.scrollable_frame)
        frame.pack(pady=5, padx=10, fill="both", expand=True)
        tableview = Tableview(frame, columns=columns, show="headings")
        for col in columns:
            tableview.heading(col, text=col)
            tableview.column(col, width=120, anchor='w')
        for row in values:
            tableview.insert("", tk.END, values=row)
        tableview.config(height=len(values) + 1 if values else 1)
        tableview.pack(side="left", fill="both", expand=True)
        return tableview

    def _tableview_values(self, tableview) -> list:
        return [list(tableview.item(item, 'values')) for item in tableview.get_children()]

    def save_tableviews_changes(self) -> None:
        common = self._tableview_values(self.common_tableview)
        if common:
            labels.apply_common_edits(self.context, common[0], labels.TEN_X_COMMON_FIELDS)
        labels.apply_variant_edits(
            self.context['main_variants'], labels.MAIN_VARIANT_FIELDS, self._tableview_values(self.main_tableview)
        )

    def save_docx_lpwgs(self) -> None:
        self.save_tableviews_changes()
        try:
            self.doc = self.clinreport.render(self.context, '10x')
        except Exception:
            messagebox.showerror("Ошибка", f"Ошибка при формировании документа: {traceback.format_exc()}", parent=self)
            return

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
            initialfile=f'Заключение LPWGS ({str(self.sample).split(".")[0]}).docx',
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
