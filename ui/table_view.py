import tkinter as tk
from tkinter import ttk, messagebox

class Tableview(ttk.Treeview):
    """Editable Treeview with forced dark text on light background"""
    
    def __init__(self, master=None, **kwargs):
        self._enable_similar_variants = bool(kwargs.pop("enable_similar_variants", False))
        super().__init__(master, **kwargs)
        self._setup_table_style()
        self._text_editor = None
        self._scrollbar = None
        self._similar_vars_button = None
        self.bind("<Double-1>", self._on_double_click)
        

    def _setup_table_style(self):
        style = ttk.Style(self)

        style.configure("Treeview",
            background="white",
            foreground="black",
            fieldbackground="white",
            borderwidth=1,
            relief="solid",
            font=('Helvetica', 10),
            selectbackground="white",  
            selectforeground="black"
            )

        style.map('Treeview', 
            background=[('selected', 'white')],  
            foreground=[('selected', 'black')]   
            )
        
    
    def _on_double_click(self, event):
        region = self.identify("region", event.x, event.y)
        if region != "cell":
            return

        row_id = self.identify_row(event.y)
        col_id = self.identify_column(event.x)

        if not row_id or not col_id:
            return

        x, y, width, height = self.bbox(row_id, col_id)

        col_num = int(col_id.replace("#", "")) - 1
        item_values = list(self.item(row_id, "values"))
        if col_num >= len(item_values):
            return
        cell_value = item_values[col_num]

        if self._text_editor:
            self._text_editor.destroy()
        if self._scrollbar:
            self._scrollbar.destroy()

        self._text_editor = tk.Text(
            self,
            wrap="word",
            height=4,
            bg="white",
            fg="black",
            insertbackground="black",
            selectbackground="gray",
            selectforeground="white"
        )
        self._text_editor.insert("1.0", cell_value)
        self._text_editor.focus_set()

        self._scrollbar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self._text_editor.yview
        )
        self._text_editor.configure(yscrollcommand=self._scrollbar.set)

        self._text_editor.place(x=x, y=y, width=width-15, height=height*4)
        self._scrollbar.place(x=x + width - 15, y=y, width=15, height=height*4)

        self._text_editor.bind("<FocusOut>", lambda e: self._save_edit(row_id, col_num))
        self._text_editor.bind("<Control-Return>", lambda e: self._save_edit(row_id, col_num, event=e))
        self._text_editor.bind("<Shift-Return>", lambda e: self._save_edit(row_id, col_num, event=e))
        self._text_editor.bind("<Escape>", lambda e: self._cancel_edit())

        if self._similar_vars_button:
            self._similar_vars_button.destroy()
            self._similar_vars_button = None

        # Optional: show "Similar variants" only when supported by parent window.
        if self._enable_similar_variants and "Ген" in self["columns"]:
            parent_window = self.winfo_toplevel()
            if hasattr(parent_window, "show_similar_variants"):
                self._similar_vars_button = tk.Button(
                    self,
                    text="Похожие варианты",
                    command=lambda: self._show_similar_variants(row_id),
                    bg="white",
                    fg="black"
                )
                self._similar_vars_button.place(x=x + width, y=y, width=120, height=height * 4)
    
    def _show_similar_variants(self, row_id):
        values = self.item(row_id, 'values')
        columns = self['columns']
        variant_data = dict(zip(columns, values))
        parent_window = self.winfo_toplevel()
        try:
            parent_window.show_similar_variants(variant_data)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть похожие варианты: {repr(e)}")

        
    def _save_edit(self, row_id, col_num, event=None):
        if event:
            event.widget.master.focus_set()  # Чтобы убрать фокус с Text (закрыть клавиатурный ввод)
        new_text = self._text_editor.get("1.0", "end-1c")

        # Получаем текущие значения строки
        values = list(self.item(row_id, "values"))
        values[col_num] = new_text
        self.item(row_id, values=values)

        self._text_editor.destroy()
        self._scrollbar.destroy()
        self._text_editor = None
        self._scrollbar = None


    def _cancel_edit(self):
        if self._text_editor:
            self._text_editor.destroy()
            self._text_editor = None
        if self._scrollbar:
            self._scrollbar.destroy()
            self._scrollbar = None