import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from ui.table_view import Tableview
from ui import labels


class ConfirmationWindow(tk.Toplevel):
    """Окно подтверждения данных одного образца (стандартный отчёт).

    Работает с context-словарём (build_context): таблицы заполняются из него,
    правки пишутся обратно в него, документ формируется через render(context).
    """

    def __init__(self, master, sample, context: dict):
        super().__init__(master)
        self.clinreport = self.master.clinreport
        self.sample = sample
        self.context = context
        self.title(f"Образец {self.sample}")
        self.geometry("850x850")
        self.style = ttk.Style(self)
        self.style.configure('Treeview', rowheight=40)

        # --- actions row ---
        self.actions_frame = ttk.Frame(self)
        self.actions_frame.pack(pady=8)

        ttk.Label(self.actions_frame, text="Шаблон:").pack(side="left", padx=(6, 2))
        self.template_var = tk.StringVar(value='DZM')
        self.template_combo = ttk.Combobox(
            self.actions_frame, textvariable=self.template_var,
            values=('DZM', 'FND'), width=6, state='readonly',
        )
        self.template_combo.pack(side="left", padx=(0, 10))

        self.save_button = tk.Button(self.actions_frame, text="Сохранить как ...", command=self.save_docx)
        self.save_button.pack(side="left", padx=6)
        self.upload_button = tk.Button(self.actions_frame, text="Выгрузить в базу", command=self.insert_to_db)
        self.upload_button.pack(side="left", padx=6)
        self.close_button = tk.Button(self.actions_frame, text="Закрыть", command=self.close)
        self.close_button.pack(side="left", padx=6)

        # --- scrollable area ---
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

    # --- scrolling ---
    def bind_mousewheel_recursively(self, widget):
        widget.bind("<MouseWheel>", self._on_mousewheel)
        for child in widget.winfo_children():
            self.bind_mousewheel_recursively(child)

    def _on_mousewheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(int(-1 * event.delta), "units")

    # --- population ---
    def pack_tableviews(self) -> None:
        common_labels = [label for _, _, label in labels.COMMON_FIELDS]
        self.common_tableview = self._pack_table(common_labels, labels.common_values(self.context))

        self.variant_tableviews = []  # list of (context_key, fields, tableview)
        for context_key, title, fields in labels.DEFAULT_VARIANT_TABLES:
            rows = self.context.get(context_key, [])
            ttk.Label(self.scrollable_frame, text=title, font=('Helvetica', 10, 'bold')).pack(pady=(10, 0))
            column_labels = [labels.FIELD_LABELS[field] for field in fields]
            values = labels.variant_rows_to_values(rows, fields)
            tableview = self._pack_table(column_labels, values, variant_rows=rows)
            self.variant_tableviews.append((context_key, fields, tableview))

    def _pack_table(self, columns, values, variant_rows=None) -> Tableview:
        frame = ttk.Frame(self.scrollable_frame)
        frame.pack(pady=5, padx=10, fill="both", expand=True)

        tableview = Tableview(frame, columns=columns, show="headings")
        for col in columns:
            tableview.heading(col, text=col)
            tableview.column(col, width=120, anchor='w')
        for i, row in enumerate(values):
            tableview.insert("", tk.END, values=row, tags=(i,))
        tableview.config(height=len(values) + 1 if values else 1)
        tableview.pack(side="left", fill="both", expand=True)

        if variant_rows:
            button_frame = ttk.Frame(frame)
            button_frame.pack(side="right", fill="y")
            for variant in variant_rows:
                tk.Button(
                    button_frame, text="Похожие", width=8,
                    command=lambda v=variant: self.show_similar_variants(v),
                ).pack(pady=2)
        return tableview

    # --- editing: write tableview edits back into the context ---
    def _tableview_values(self, tableview) -> list:
        return [list(tableview.item(item, 'values')) for item in tableview.get_children()]

    def save_tableviews_changes(self) -> None:
        common = self._tableview_values(self.common_tableview)
        if common:
            labels.apply_common_edits(self.context, common[0])
        for context_key, fields, tableview in self.variant_tableviews:
            labels.apply_variant_edits(self.context[context_key], fields, self._tableview_values(tableview))

    # --- actions ---
    def save_docx(self) -> None:
        self.save_tableviews_changes()
        try:
            self.doc = self.clinreport.render(self.context, self.template_var.get())
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
            initialfile=f'Заключение ({str(self.sample).split(".")[0]}).docx',
        )
        try:
            self.attributes("-topmost", False)
        except Exception:
            pass
        if filepath:
            try:
                self.doc.save(filepath)
                # NOTE: DB auto-upload returns in step 3c.
                messagebox.showinfo("Успешно", "Документ сохранен", parent=self)
            except Exception as e:
                messagebox.showerror("Ошибка", f"Ошибка при сохранении документа: {repr(e)}", parent=self)

    def insert_to_db(self) -> None:
        # DB upload is rewired in step 3c (payload built from the new context dict).
        messagebox.showinfo("В разработке", "Выгрузка в базу будет доступна после шага 3c.", parent=self)

    def show_similar_variants(self, variant) -> None:
        # Similar-variants DB lookup is rewired in step 3c.
        messagebox.showinfo("В разработке", "Поиск похожих вариантов будет доступен после шага 3c.", parent=self)

    def close(self) -> None:
        self.destroy()
