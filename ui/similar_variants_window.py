import tkinter as tk
from tkinter import ttk

class SimilarVariantsWindow(tk.Toplevel):
    """Окно для отображения похожих вариантов из базы данных"""
    
    def __init__(self, master, variant_data):
        super().__init__(master)
        self.title(f"Похожие варианты для {variant_data['Ген']}")
        self.geometry("800x600")
        
        
        # Получаем данные о похожих вариантах из БД
        similar_variants = self.get_similar_variants(variant_data)
        
        # Создаем таблицу для отображения
        self.tree = ttk.Treeview(self, columns=('Образец', 'Патогенность', 'Клиницист', 'Дата заключения'), show='headings')
        self.tree.heading('Образец', text='Образец')
        self.tree.heading('Патогенность', text='Патогенность')
        self.tree.heading('Клиницист', text='Клиницист')
        self.tree.heading('Дата заключения', text='Дата заключения')
        
        # Заполняем таблицу данными
        for variant in similar_variants:
            self.tree.insert('', 'end', values=(
                variant['Номер образца'],
                variant['Патогенность'],
                variant['Клиницист'],
                variant['Дата заключения']
            ))
        
        self.tree.pack(fill='both', expand=True)