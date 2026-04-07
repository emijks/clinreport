import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from ui.table_view import Tableview

class ConfirmationWindow(tk.Toplevel):
    """Окно подтверждения данных."""

    def __init__(self, master, sample: str, lpwgs_target: bool = False):
        super().__init__(master)
        self.database = self.master.database
        self.clinreport = self.master.clinreport
        self.sample = sample
        self.lpwgs_target = lpwgs_target
        self.title(f"Образец {self.sample}")
        self.geometry("850x850")
        self.style = ttk.Style(self)
        self.style.configure('Treeview', rowheight=40)

        # Action buttons row (horizontal)
        self.actions_frame = ttk.Frame(self)
        self.actions_frame.pack(pady=8)

        self.save_button = tk.Button(self.actions_frame, text="Сохранить как ...", command=self.save_docx)
        self.save_button.pack(side="left", padx=6)

        self.upload_button = tk.Button(self.actions_frame, text="Выгрузить в базу", command=self.insert_to_db)
        self.upload_button.pack(side="left", padx=6)

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
            self.canvas.yview_scroll(int(-1*(event.delta)), "units")
        else:
            pass


    def pack_tableviews(self) -> None:
        sample_data = self.clinreport.data[self.sample]
        sample_variants_data = sample_data['variants_data']

        common_columns = [
            'Номер образца',
            'Пол пациента',
            'Возраст пациента',
            'Предварительный диагноз',
            'Средняя глубина прочтения генома после секвенирования'
        ]
        common_values = [[self.clinreport.data[self.sample][col] for col in common_columns]]
        self.common_tableview = self.pack_tableview(common_columns, common_values)

        self.variants_tableviews = {}
        for note, columns in zip(['1', '2', '3', '7', '8'], [self.clinreport.SNV_table_header + ("Ручные критерии",)]*4+[self.clinreport.C_table_header + ("Ручные критерии",)]):
            note_variants_data = self.clinreport.filter_variants(sample_variants_data, by_note=note)
            variants_rows = [[row[col] for col in columns] for row in note_variants_data]
            self.variants_tableviews[note] = self.pack_tableview_with_buttons(columns, variants_rows, note_variants_data)

    def pack_tableview_with_buttons(self, columns: list | tuple, rows: list, variants_data: list):
        # Создаем фрейм для таблицы и кнопок
        frame = ttk.Frame(self.scrollable_frame)
        frame.pack(pady=10, padx=10, fill="both", expand=True)
        
        # Создаем таблицу
        tableview = Tableview(frame, columns=columns, show="headings")
        for col in columns:
            tableview.heading(col, text=col)
            tableview.column(col, width=100)
        
        # Заполняем таблицу данными
        for i, row in enumerate(rows):
            tableview.insert("", tk.END, values=row, tags=(i,))
        
        tableview.config(height=len(rows)+3 if len(rows) else 0)
        tableview.pack(side="left", fill="both", expand=True)
        
        # Создаем фрейм для кнопок
        button_frame = ttk.Frame(frame)
        button_frame.pack(side="right", fill="y")
        
        # Добавляем кнопки для каждой строки
        for i, variant_data in enumerate(variants_data):
            btn = tk.Button(
                button_frame,
                text="Похожие",
                command=lambda vd=variant_data: self.show_similar_variants(vd),
                width=8
            )
            btn.pack(pady=2)
        
        return tableview

    def show_similar_variants(self, variant_data):
        """Показывает похожие варианты из базы данных"""
        similar_window = tk.Toplevel(self)
        similar_window.title(f"Похожие варианты для {variant_data['Ген']}")
        similar_window.geometry("800x400")
        
        
        try:
            # Получаем похожие варианты из базы данных
            similar_variants = self.master.database.get_similar_variants(variant_data)
            
            # Создаем таблицу для отображения
            columns = ['Образец', 'Патогенность', 'Клиницист', 'Дата заключения']
            tree = ttk.Treeview(similar_window, columns=columns, show="headings")
            
            for col in columns:
                tree.heading(col, text=col)
                tree.column(col, width=150)
            
            for variant in similar_variants:
                tree.insert("", tk.END, values=(
                    variant['Номер образца'],
                    variant['Патогенность'],
                    variant['Клиницист'],
                    variant['Дата заключения']
                ))
            
            tree.pack(fill="both", expand=True)
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось получить данные: {str(e)}")

    def pack_tableview(self, columns: list | tuple, rows: list, variants_data: list | None = None) -> ttk.Treeview:
        """
        Создает и размещает таблицу с данными и кнопками для поиска похожих вариантов
        
        Args:
            columns: Заголовки столбцов
            rows: Данные для строк таблицы
            variants_data: Список словарей с полными данными вариантов (для поиска похожих)
        
        Returns:
            Созданный виджет таблицы
        """
        # Создаем основной фрейм для таблицы и кнопок
        container = ttk.Frame(self.scrollable_frame)
        container.pack(fill='x', pady=5, padx=10)
        
        # Создаем таблицу
        tableview = Tableview(container, columns=columns, show="headings")
        
        # Настраиваем заголовки и ширину столбцов
        for col in columns:
            tableview.heading(col, text=col)
            tableview.column(col, width=100, anchor='w')
        
        # Заполняем таблицу данными
        for row in rows:
            tableview.insert("", tk.END, values=row)
        
        tableview.pack(side='left', fill='x', expand=True)
        
        # Если переданы данные вариантов, добавляем кнопки
        if variants_data:
            # Фрейм для кнопок
            button_frame = ttk.Frame(container)
            button_frame.pack(side='right', fill='y')
            
            # Добавляем кнопку "Похожие" для каждой строки
            for i, variant in enumerate(variants_data):
                btn = tk.Button(
                    button_frame,
                    text="Похожие",
                    command=lambda v=variant: self.show_similar_variants(v),
                    width=8
                )
                btn.pack(pady=2, padx=2)
        
        return tableview


    def save_tableviews_changes(self) -> None:
        common_tableview_changes = self.get_tableview_changes(self.common_tableview)[0]
        self.clinreport.data[self.sample].update(common_tableview_changes)

        for note, variants_tableview in self.variants_tableviews.items():
            note_variants_tableview_changes = self.get_tableview_changes(variants_tableview)
            j = 0
            for i, sample_variant_data in enumerate(self.clinreport.data[self.sample]['variants_data']):
                if sample_variant_data['base__note'] != note:
                    continue
                self.clinreport.data[self.sample]['variants_data'][i].update(note_variants_tableview_changes[j])
                j += 1


    def get_tableview_changes(self, tableview) -> list:
        tableview_changes = []
        for item in tableview.get_children():
            values = tableview.item(item, 'values')
            tableview_changes.append(dict(zip(tableview['columns'], values)))
        return tableview_changes


    def save_docx(self) -> None:
        """Сохраняет документ и при необходимости выгружает в БД."""

        self.save_tableviews_changes()

        if self.lpwgs_target:
            self.doc = self.clinreport.create_doc(self.sample)
        else:
            self.doc = self.clinreport.create_doc(self.sample)

        # Ensure save dialog appears in front of this window.
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
            initialfile=f'Заключение ({str(self.sample).split(".")[0]}).docx'
        )
        try:
            self.attributes("-topmost", False)
        except Exception:
            pass
        if filepath:
            try:
                self.doc.save(filepath)

                if self.master.config.get('auto_upload', True):
                    self.insert_to_db()
                    messagebox.showinfo("Успешно", "Документ сохранен и данные выгружены в БД", parent=self)
                else:
                    messagebox.showinfo("Успешно", "Документ сохранен", parent=self)
                    
            except Exception as e:
                messagebox.showerror("Ошибка", f"Ошибка при сохранении документа: {repr(e)}", parent=self)


    def insert_to_db(self) -> None:
        try:
            sample_name = str(self.sample).split(".")[0]
            if self.database.sample_data_exists(sample_name):
                answer = messagebox.askyesno(
                    "Найден дубликат образца",
                    f'Для образца "{sample_name}" есть записи в БД. Вы хотите записать еще?'
                )
                if not answer:
                    return
            sample_payload = self.clinreport.sample_data_to_payload(self.clinreport.data[self.sample])
            self.database.insert(sample_payload)
            messagebox.showinfo("Успешно", f"{len(sample_payload)} вариант(ов) успешно выгружены")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при выгрузке данных: {repr(e)}")


    def close(self) -> None:
        self.destroy()