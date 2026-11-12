"""
HOI4 Focus & Idea Editor v2.0
Запуск: python hoi4_editor.py
Опционально: pip install Pillow (для предпросмотра .dds)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import json
import os
import re
import shutil

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ===================================================== Tooltip

class Tooltip:
    def __init__(self, widget, text, delay=400):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tip = None
        self.after_id = None
        widget.bind("<Enter>", self._sched, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _sched(self, e=None):
        self._cancel()
        self.after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self.after_id:
            try:
                self.widget.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None

    def _show(self):
        if self.tip:
            return
        x = self.widget.winfo_rootx() + 15
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry("+%d+%d" % (x, y))
        tk.Label(self.tip, text=self.text, justify=tk.LEFT, bg="#ffffcc",
                 relief=tk.SOLID, bd=1, font=("Tahoma", 9), wraplength=340,
                 padx=6, pady=4).pack()

    def _hide(self, e=None):
        self._cancel()
        if self.tip:
            self.tip.destroy()
            self.tip = None


# ===================================================== Модели

class Focus:
    def __init__(self, fid):
        self.id = fid
        self.title = fid.replace("_", " ").title()
        self.description = ""
        self.icon = "GFX_focus_generic_industry"
        self.image_file = ""
        self.x = 0
        self.y = 0
        self.cost = 10
        self.prereq_groups = []   # [[a, b], [c]] = (A ИЛИ B) И C
        self.effects = ""

    @property
    def prerequisites(self):
        """Плоский вид (для совместимости со старыми сохранениями)."""
        return [p for group in self.prereq_groups for p in group]

    def to_dict(self):
        d = self.__dict__.copy()
        d["prereq_groups"] = [list(g) for g in self.prereq_groups]
        return d

    @classmethod
    def from_dict(cls, d):
        f = cls(d.get("id", "focus"))
        for k, v in d.items():
            if k in ("prerequisites", "prereq_groups"):
                continue
            if hasattr(f, k):
                setattr(f, k, v)
        if "prereq_groups" in d:
            f.prereq_groups = [list(g) for g in (d["prereq_groups"] or [])]
        elif "prerequisites" in d:
            f.prereq_groups = [[p] for p in (d["prerequisites"] or [])]
        return f


class Idea:
    def __init__(self, iid):
        self.id = iid
        self.category = "country"
        self.name_text = iid.replace("_", " ").title()
        self.desc_text = ""
        self.picture = "GFX_idea_generic_political_advisor_europe_1"
        self.image_file = ""     # путь к своему изображению (опционально)
        self.modifier = ""
        self.allowed = "always = yes"
        self.available = "always = yes"
        self.visible = "always = yes"
        self.removal_cost = 0

    def to_dict(self):
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d):
        i = cls(d.get("id", "idea"))
        for k, v in d.items():
            if hasattr(i, k):
                setattr(i, k, v)
        return i


# ===================================================== Константы

FOCUS_ICONS = [
    "GFX_focus_generic_industry",
    "GFX_focus_generic_military",
    "GFX_focus_generic_political",
    "GFX_focus_generic_diplomacy",
    "GFX_focus_generic_intelligence",
    "GFX_focus_generic_navy",
    "GFX_focus_generic_air",
    "GFX_focus_generic_army",
    "GFX_focus_generic_research",
    "GFX_focus_generic_construction",
]

IDEA_CATEGORIES = [
    "country", "law", "political_advisor", "theorist",
    "army_chief", "navy_chief", "air_chief", "high_command",
    "tank_designer", "ship_designer", "plane_designer",
    "material_designer", "industrial_concern",
]

IDEA_PICTURES = [
    "GFX_idea_generic_political_advisor_europe_1",
    "GFX_idea_generic_army_chief_1",
    "GFX_idea_generic_navy_chief_1",
    "GFX_idea_generic_air_chief_1",
    "GFX_idea_generic_theorist_1",
]

# Категоризированные быстрые эффекты для фокусов
FOCUS_EFFECTS = {
    "💰 Политика": [
        ("Политвласть +100", "add_political_power = 100"),
        ("Политвласть +150", "add_political_power = 150"),
        ("Стабильность +5%", "add_stability = 0.05"),
        ("Стабильность +10%", "add_stability = 0.10"),
        ("Воен. поддержка +5%", "add_war_support = 0.05"),
        ("Воен. поддержка +10%", "add_war_support = 0.10"),
        ("Командный дух +10", "add_command_power = 10"),
        ("Смена идеологии", "set_politics = { ruling_party = fascism elections_allowed = no }"),
    ],
    "⚔️ Армия": [
        ("Опыт армии +10", "add_army_experience = 10"),
        ("Опыт армии +25", "add_army_experience = 25"),
        ("Скорость армии +5%", "army_speed_factor = 0.05"),
        ("Урон +5%", "damage_factor = 0.05"),
        ("Защита +5%", "defense_factor = 0.05"),
        ("Прорыв +5%", "breakthrough_factor = 0.05"),
        ("Планирование +5%", "planning_speed = 0.05"),
        ("Обучение -5%", "training_time_factor = -0.05"),
    ],
    "🏭 Промышленность": [
        ("Фабрика +1", "add_offsite_building = { type = industrial_complex level = 1 }"),
        ("Воензавод +1", "add_offsite_building = { type = arms_factory level = 1 }"),
        ("Верфь +1", "add_offsite_building = { type = dockyard level = 1 }"),
        ("Строительство +5%", "production_speed_buildings_factor = 0.05"),
        ("Пром. мощность +5%", "industrial_capacity_factory = 0.05"),
        ("Эффективность +5%", "production_efficiency_cap_factor = 0.05"),
        ("Товары нар. -5%", "consumer_goods_factor = -0.05"),
        ("Ресурсы +5%", "resource_gain_factor = 0.05"),
    ],
    "🔬 Наука": [
        ("Скорость иссл. +5%", "research_speed_factor = 0.05"),
        ("Скорость иссл. +10%", "research_speed_factor = 0.10"),
        ("Слот исследователя +1", "research_slot = 1"),
        ("Пром. технологии +5%", "industrial_research_speed = 0.05"),
        ("Электроника +5%", "electronics_research_speed = 0.05"),
        ("Артиллерия +5%", "artillery_research_speed = 0.05"),
        ("Доктрины +5%", "land_doctrine_research_speed = 0.05"),
    ],
    "✈️ Авиация": [
        ("Опыт авиации +10", "add_air_experience = 10"),
        ("Опыт авиации +25", "add_air_experience = 25"),
        ("Мощность авиации +5%", "air_mission_efficiency = 0.05"),
        ("Превосходство +5%", "air_superiority_efficiency = 0.05"),
        ("ПВО +5%", "air_defense_factor = 0.05"),
    ],
    "⚓ Флот": [
        ("Опыт флота +10", "add_navy_experience = 10"),
        ("Опыт флота +25", "add_navy_experience = 25"),
        ("Скорость флота +5%", "navy_speed_factor = 0.05"),
        ("Урон флота +5%", "navy_damage_factor = 0.05"),
        ("Защита флота +5%", "navy_defense_factor = 0.05"),
    ],
    "🌍 Дипломатия": [
        ("Отношения +25", "add_opinion = { target = GER modifier = 25 }"),
        ("Гарантия", "give_guarantee = GER"),
        ("Создать фракцию", "create_faction = my_faction"),
        ("Присоединить к фракции", "add_to_faction = GER"),
        ("Создать альянс", "add_to_war = { targeted_alliance = GER }"),
    ],
    "🎯 Особое": [
        ("Добавить идею", "add_ideas = { my_idea }"),
        ("Убрать идею", "remove_ideas = { my_idea }"),
        ("Технология", "add_tech_bonus = { name = my_bonus bonus = 1 uses = 1 category = infantry }"),
        ("Разблокировать решение", "unlock_decision_tooltip = my_decision"),
        ("Создать решение", "activate_decision = my_decision"),
        ("Событие", "country_event = my_events.1"),
        ("Снаряжение", "add_equipment_to_stockpile = { type = infantry_equipment amount = 1000 }"),
        ("Открыть страну", "release_puppet = GER"),
    ],
}

# Категоризированные быстрые модификаторы для идей
IDEA_MODIFIERS = {
    "💰 Политика": [
        ("Политвласть +10%", "political_power_factor = 0.1"),
        ("Стабильность +5%", "stability_factor = 0.05"),
        ("Воен. поддержка +5%", "war_support_factor = 0.05"),
        ("Командный дух +10%", "command_power_gain = 0.1"),
    ],
    "⚔️ Армия": [
        ("Скорость армии +5%", "army_speed_factor = 0.05"),
        ("Урон +5%", "damage_factor = 0.05"),
        ("Защита +5%", "defense_factor = 0.05"),
        ("Прорыв +5%", "breakthrough_factor = 0.05"),
    ],
    "🏭 Промышленность": [
        ("Строительство +5%", "production_speed_buildings_factor = 0.05"),
        ("Пром. мощность +5%", "industrial_capacity_factory = 0.05"),
        ("Товары нар. -5%", "consumer_goods_factor = -0.05"),
    ],
    "🔬 Наука": [
        ("Скорость иссл. +5%", "research_speed_factor = 0.05"),
        ("Пром. технологии +5%", "industrial_research_speed = 0.05"),
    ],
}


# ===================================================== Редактор

class HOI4Editor:
    GRID_X = 240
    GRID_Y = 160
    FW = 220
    FH = 120

    def __init__(self, root):
        self.root = root
        self.root.title("HOI4 Focus & Idea Editor v2.0")
        self.root.geometry("1500x900")
        self.root.minsize(1150, 650)

        self.focuses = {}
        self.selected_focus = None
        self.drag = None
        self.connect_mode = False
        self.connect_logic = tk.StringVar(value="AND")
        self.connect_src = None
        self.cv_items = {}
        self.focus_previews = {}   # fid -> PhotoImage (canvas refs)

        self.ideas = {}
        self.selected_idea = None

        self.mod_name = "My Mod"
        self.mod_folder = "my_mod"
        self.mod_tag = "GER"
        self.tree_id = "my_focus_tree"
        self.mod_factor = 100

        self._build_ui()
        self._draw_grid()
        if HAS_PIL:
            self.set_hint("Нажмите «＋ Фокус», чтобы создать первый фокус. "
                          "Свою картинку можно выбрать в свойствах фокуса.")
        else:
            self.set_hint("Нажмите «＋ Фокус». Для предпросмотра .dds установите: "
                          "pip install Pillow")

    def set_hint(self, text):
        self.hint_var.set("💡 " + text)

    # ---------- UI ----------

    def _build_ui(self):
        mb = tk.Menu(self.root)
        fm = tk.Menu(mb, tearoff=0)
        fm.add_command(label="Новый", command=self.new_project, accelerator="Ctrl+N")
        fm.add_command(label="Открыть...", command=self.load_project, accelerator="Ctrl+O")
        fm.add_command(label="Сохранить...", command=self.save_project, accelerator="Ctrl+S")
        fm.add_separator()
        fm.add_command(label="Экспорт мода...", command=self.export_mod, accelerator="Ctrl+E")
        fm.add_separator()
        fm.add_command(label="Выход", command=self.root.quit)
        mb.add_cascade(label="Файл", menu=fm)
        hm = tk.Menu(mb, tearoff=0)
        hm.add_command(label="Инструкция", command=self.show_help)
        hm.add_command(label="О программе", command=self.show_about)
        mb.add_cascade(label="Справка", menu=hm)
        self.root.config(menu=mb)

        self.root.bind("<Control-n>", lambda e: self.new_project())
        self.root.bind("<Control-o>", lambda e: self.load_project())
        self.root.bind("<Control-s>", lambda e: self.save_project())
        self.root.bind("<Control-e>", lambda e: self.export_mod())

        top = ttk.Frame(self.root, padding=(6, 4))
        top.pack(side=tk.TOP, fill=tk.X)
        b_set = ttk.Button(top, text="⚙ Настройки мода", command=self.mod_settings)
        b_set.pack(side=tk.LEFT, padx=2)
        Tooltip(b_set, "Название мода, папка, тег страны и приоритет дерева.")
        b_help = ttk.Button(top, text="❓ Инструкция", command=self.show_help)
        b_help.pack(side=tk.LEFT, padx=2)
        b_exp = ttk.Button(top, text="📤 Экспорт мода", command=self.export_mod)
        b_exp.pack(side=tk.RIGHT, padx=2)
        Tooltip(b_exp, "Соберёт папку мода, .mod-файл и .gfx для своих картинок.\n"
                       "Скопируйте папку и .mod в:\n"
                       "Documents/Paradox Interactive/Hearts of Iron IV/mod/")

        self.status_var = tk.StringVar(value="Готово")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN,
                  anchor=tk.W, padding=(6, 2)).pack(side=tk.BOTTOM, fill=tk.X)
        self.hint_var = tk.StringVar(value="")
        ttk.Label(self.root, textvariable=self.hint_var, anchor=tk.W,
                  padding=(6, 4), foreground="#1144aa").pack(side=tk.BOTTOM, fill=tk.X)

        nb = ttk.Notebook(self.root)
        nb.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.focus_tab = ttk.Frame(nb)
        nb.add(self.focus_tab, text="🌳 Фокусы")
        self.idea_tab = ttk.Frame(nb)
        nb.add(self.idea_tab, text="💡 Идеи")
        self._build_focus_tab()
        self._build_idea_tab()

    # ===================================================== ФОКУСЫ

    def _build_focus_tab(self):
        tb = ttk.Frame(self.focus_tab, padding=(6, 4))
        tb.pack(side=tk.TOP, fill=tk.X)
        b_add = ttk.Button(tb, text="＋ Фокус", command=self.focus_add)
        b_add.pack(side=tk.LEFT, padx=2)
        Tooltip(b_add, "Создать новый фокус.")
        self.b_connect = ttk.Button(tb, text="🔗 Соединить", command=self.toggle_connect)
        self.b_connect.pack(side=tk.LEFT, padx=2)
        Tooltip(self.b_connect, "Режим соединения: клик на ПРЕДПОСЫЛКУ, затем на ЗАВИСИМЫЙ.")

        ttk.Label(tb, text=" Логика:").pack(side=tk.LEFT)
        rb_and = ttk.Radiobutton(tb, text="AND", variable=self.connect_logic, value="AND")
        rb_and.pack(side=tk.LEFT)
        Tooltip(rb_and, "Новая связь = ОТДЕЛЬНАЯ группа.\n"
                        "Пример: A AND B — оба обязательны.")
        rb_or = ttk.Radiobutton(tb, text="OR", variable=self.connect_logic, value="OR")
        rb_or.pack(side=tk.LEFT)
        Tooltip(rb_or, "Новая связь = В ПОСЛЕДНЮЮ группу (OR).\n"
                       "Пример: A OR B — достаточно любой.\n"
                       "Если групп нет — создастся новая.")
        b_del = ttk.Button(tb, text="🗑 Удалить", command=self.focus_delete)
        b_del.pack(side=tk.LEFT, padx=2)
        b_dup = ttk.Button(tb, text="📋 Дублировать", command=self.focus_dup)
        b_dup.pack(side=tk.LEFT, padx=2)
        Tooltip(b_dup, "Создать копию выделенного фокуса с новым ID.")

        b_save = ttk.Button(tb, text="💾 Применить", command=self.focus_apply)
        b_save.pack(side=tk.RIGHT, padx=2)

        paned = ttk.PanedWindow(self.focus_tab, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(paned, width=200)
        paned.add(left, weight=0)
        ttk.Label(left, text="Список фокусов", font=("", 10, "bold")).pack(anchor=tk.W, padx=6, pady=(6, 2))
        lw = ttk.Frame(left)
        lw.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.focus_list = tk.Listbox(lw, exportselection=False)
        sb = ttk.Scrollbar(lw, orient=tk.VERTICAL, command=self.focus_list.yview)
        self.focus_list.config(yscrollcommand=sb.set)
        self.focus_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.focus_list.bind("<<ListboxSelect>>", self._on_focus_list_select)

        center = ttk.Frame(paned)
        paned.add(center, weight=1)
        cw = ttk.Frame(center)
        cw.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(cw, bg="#2b2b2b",
                                scrollregion=(0, 0, 4000, 2600),
                                highlightthickness=0)
        hs = ttk.Scrollbar(cw, orient=tk.HORIZONTAL, command=self.canvas.xview)
        vs = ttk.Scrollbar(cw, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.config(xscrollcommand=hs.set, yscrollcommand=vs.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        cw.rowconfigure(0, weight=1)
        cw.columnconfigure(0, weight=1)
        self.canvas.bind("<ButtonPress-1>", self._cv_press)
        self.canvas.bind("<B1-Motion>", self._cv_drag)
        self.canvas.bind("<ButtonRelease-1>", self._cv_release)
        self.canvas.bind("<Button-3>", self._cv_right)
        self.canvas.bind("<MouseWheel>", self._cv_wheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))

        right = ttk.Frame(paned, width=460)
        paned.add(right, weight=0)
        self._build_focus_props(right)

    def _build_focus_props(self, parent):
        ttk.Label(parent, text="Свойства фокуса", font=("", 10, "bold")).pack(anchor=tk.W, padx=6, pady=(6, 2))
        nb = ttk.Notebook(parent)
        nb.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        basic = ttk.Frame(nb, padding=8)
        nb.add(basic, text="Основное")
        eff = ttk.Frame(nb, padding=8)
        nb.add(eff, text="Эффекты")

        # --- основное
        r = ttk.Frame(basic); r.pack(fill=tk.X, pady=2)
        ttk.Label(r, text="ID:", width=14).pack(side=tk.LEFT)
        self.f_id = tk.StringVar()
        ttk.Entry(r, textvariable=self.f_id).pack(side=tk.LEFT, fill=tk.X, expand=True)

        r = ttk.Frame(basic); r.pack(fill=tk.X, pady=2)
        ttk.Label(r, text="Название:", width=14).pack(side=tk.LEFT)
        self.f_title = tk.StringVar()
        ttk.Entry(r, textvariable=self.f_title).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # --- картинка
        ttk.Label(basic, text="Иконка фокуса:", font=("", 9, "bold")).pack(anchor=tk.W, pady=(8, 2))

        r = ttk.Frame(basic); r.pack(fill=tk.X, pady=2)
        ttk.Label(r, text="Стандартная:", width=14).pack(side=tk.LEFT)
        self.f_icon = tk.StringVar()
        cb = ttk.Combobox(r, textvariable=self.f_icon, values=FOCUS_ICONS, state="normal")
        cb.pack(side=tk.LEFT, fill=tk.X, expand=True)
        Tooltip(cb, "Имя GFX-иконки из ванилы.\n"
                    "Если хотите свою — нажмите кнопку «📁 Своя картинка» ниже.")

        r = ttk.Frame(basic); r.pack(fill=tk.X, pady=2)
        b_pick = ttk.Button(r, text="📁 Своя картинка (DDS/PNG)...", command=self.pick_focus_image)
        b_pick.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        Tooltip(b_pick, "Выбрать своё изображение с диска.\n"
                        "Рекомендуется 156×108 .dds (как у ванильных фокусов) или .png.\n"
                        "При экспорте автоматически попадёт в gfx/interface/goals/custom/.")
        b_reset = ttk.Button(r, text="✖ Сброс", command=self.reset_focus_image, width=10)
        b_reset.pack(side=tk.LEFT)
        Tooltip(b_reset, "Вернуть стандартную иконку (убрать свою картинку).")

        # превью
        self.f_preview_frame = tk.Label(basic, text="(нет своей картинки)",
                                        bg="#333", fg="#999", width=20, height=5,
                                        relief=tk.SUNKEN, bd=1)
        self.f_preview_frame.pack(pady=4)
        self.f_preview_label = self.f_preview_frame

        r = ttk.Frame(basic); r.pack(fill=tk.X, pady=2)
        ttk.Label(r, text="Стоимость:", width=14).pack(side=tk.LEFT)
        self.f_cost = tk.IntVar(value=10)
        ttk.Spinbox(r, from_=1, to=100, textvariable=self.f_cost, width=6).pack(side=tk.LEFT)
        ttk.Label(r, text="  X:").pack(side=tk.LEFT)
        self.f_x = tk.IntVar(value=0)
        ttk.Spinbox(r, from_=0, to=40, textvariable=self.f_x, width=5).pack(side=tk.LEFT)
        ttk.Label(r, text=" Y:").pack(side=tk.LEFT)
        self.f_y = tk.IntVar(value=0)
        ttk.Spinbox(r, from_=0, to=40, textvariable=self.f_y, width=5).pack(side=tk.LEFT)

        ttk.Label(basic, text="Описание:").pack(anchor=tk.W, pady=(6, 0))
        self.f_desc = tk.Text(basic, height=3, wrap=tk.WORD)
        self.f_desc.pack(fill=tk.X, pady=2)

        ttk.Label(basic, text="Предпосылки:").pack(anchor=tk.W, pady=(6, 0))
        ttk.Label(basic, text="OR внутри группы · AND между группами",
                  font=("", 8), foreground="#666").pack(anchor=tk.W)
        pf = ttk.Frame(basic); pf.pack(fill=tk.BOTH, expand=True, pady=2)
        self.f_prereq = ttk.Treeview(pf, columns=(), show="tree", height=5)
        ps = ttk.Scrollbar(pf, orient=tk.VERTICAL, command=self.f_prereq.yview)
        self.f_prereq.config(yscrollcommand=ps.set)
        self.f_prereq.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ps.pack(side=tk.RIGHT, fill=tk.Y)

        btn_row = ttk.Frame(basic); btn_row.pack(fill=tk.X, pady=2)
        b1 = ttk.Button(btn_row, text="➕ AND-группа", command=self.prereq_add_group)
        b1.pack(side=tk.LEFT, padx=1)
        Tooltip(b1, "Создать новую AND-группу с одним фокусом.\n"
                    "Если таких групп несколько — все обязательны.")
        b2 = ttk.Button(btn_row, text="➕ OR в группу", command=self.prereq_add_or)
        b2.pack(side=tk.LEFT, padx=1)
        Tooltip(b2, "Добавить фокус как OR к выбранной группе.\n"
                    "Сначала выдели группу в дереве.")
        b3 = ttk.Button(btn_row, text="🗑 Удалить", command=self.prereq_delete)
        b3.pack(side=tk.LEFT, padx=1)
        Tooltip(b3, "Удалить выбранную группу или элемент.")

        # --- эффекты (категоризированные)
        ttk.Label(eff, text="Быстрые эффекты по категориям:").pack(anchor=tk.W)
        cat_nb = ttk.Notebook(eff)
        cat_nb.pack(fill=tk.BOTH, expand=False, pady=(2, 6))
        for cat_name, items in FOCUS_EFFECTS.items():
            sub = ttk.Frame(cat_nb, padding=4)
            cat_nb.add(sub, text=cat_name[:6])
            for label, code in items:
                b = ttk.Button(sub, text=label,
                               command=lambda c=code: self._append_effect(c))
                b.pack(fill=tk.X, pady=1)
                Tooltip(b, "Вставит код:\n" + code)

        hdr = ttk.Frame(eff); hdr.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(hdr, text="Код эффектов:").pack(side=tk.LEFT)
        b_copy = ttk.Button(hdr, text="📋 Копировать всё", command=self._copy_effects)
        b_copy.pack(side=tk.RIGHT)
        Tooltip(b_copy, "Скопировать весь текст эффектов в буфер обмена.")

        self.f_effects = tk.Text(eff, height=10, wrap=tk.WORD, font=("Consolas", 9))
        self.f_effects.pack(fill=tk.BOTH, expand=True, pady=2)

    # ---------- картинки фокусов ----------

    def pick_focus_image(self):
        if not self.selected_focus:
            self.set_hint("Сначала выберите фокус.")
            return
        path = filedialog.askopenfilename(
            title="Выберите картинку для фокуса",
            filetypes=[
                ("Изображения HOI4", "*.dds *.png *.tga *.jpg *.jpeg"),
                ("DDS (рекомендуется)", "*.dds"),
                ("PNG", "*.png"),
                ("Все файлы", "*.*"),
            ])
        if not path:
            return
        f = self.focuses[self.selected_focus]
        f.image_file = path
        f.icon = "GFX_focus_" + f.id
        self.f_icon.set(f.icon)
        self._update_focus_preview()
        self._draw_focus(f)
        self.status_var.set("Иконка: " + os.path.basename(path))
        if not HAS_PIL and not path.lower().endswith(".png"):
            self.set_hint("Файл выбран. Для предпросмотра .dds установите Pillow: pip install Pillow. "
                          "На экспорт это не влияет.")
        else:
            self.set_hint("Картинка установлена. Не забудьте «💾 Применить».")

    def reset_focus_image(self):
        if not self.selected_focus:
            return
        f = self.focuses[self.selected_focus]
        f.image_file = ""
        f.icon = FOCUS_ICONS[0]
        self.f_icon.set(f.icon)
        self._update_focus_preview()
        self._draw_focus(f)
        self.status_var.set("Иконка сброшена на стандартную")

    def _update_focus_preview(self):
        if not self.selected_focus:
            self.f_preview_label.config(image="", text="(нет своей картинки)")
            return
        f = self.focuses[self.selected_focus]
        if not f.image_file or not os.path.exists(f.image_file):
            self.f_preview_label.config(image="", text="(нет своей картинки)")
            return
        photo = self._make_preview(f.image_file, (130, 90))
        if photo:
            self.f_preview_label.config(image=photo, text="", width=130, height=90)
            self.f_preview_label.image = photo
        else:
            self.f_preview_label.config(
                image="", text="⚠ Превью недоступно\n" + os.path.basename(f.image_file),
                width=20, height=4)

    def _make_preview(self, path, size=(64, 64)):
        """Возвращает PhotoImage или None. Пробует PIL, потом PNG."""
        if not path or not os.path.exists(path):
            return None
        try:
            ext = os.path.splitext(path)[1].lower()
            if HAS_PIL:
                img = Image.open(path).convert("RGBA")
                img.thumbnail(size, Image.LANCZOS)
                bg = Image.new("RGBA", size, (60, 60, 60, 255))
                bg.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2), img)
                return ImageTk.PhotoImage(bg)
            elif ext == ".png":
                img = tk.PhotoImage(file=path)
                sx = max(1, img.width() // size[0])
                sy = max(1, img.height() // size[1])
                s = max(sx, sy)
                if s > 1:
                    img = img.subsample(s, s)
                return img
        except Exception:
            return None
        return None

    # ---------- холст ----------

    def _draw_grid(self):
        for x in range(0, 4000, 60):
            self.canvas.create_line(x, 0, x, 2600, fill="#363636", tags="grid")
        for y in range(0, 2600, 60):
            self.canvas.create_line(0, y, 4000, y, fill="#363636", tags="grid")
        self.canvas.tag_lower("grid")

    def _focus_coords(self, f):
        cx = f.x * self.GRID_X + self.GRID_X // 2
        cy = f.y * self.GRID_Y + self.GRID_Y // 2
        return (cx - self.FW // 2, cy - self.FH // 2,
                cx + self.FW // 2, cy + self.FH // 2)

    def _draw_focus(self, f):
        if f.id in self.cv_items:
            for it in self.cv_items[f.id].values():
                self.canvas.delete(it)
        if f.id in self.focus_previews:
            del self.focus_previews[f.id]

        x1, y1, x2, y2 = self._focus_coords(f)
        outline = "#ffd700" if f.id == self.selected_focus else "#7a7a7a"
        width = 3 if f.id == self.selected_focus else 2
        items = {}

        items["rect"] = self.canvas.create_rectangle(
            x1, y1, x2, y2, fill="#3c3c3c", outline=outline, width=width,
            tags=("focus_" + f.id, "focus"))

        # Иконка 64x64 слева сверху
        ix1, iy1 = x1 + 8, y1 + 8
        ix2, iy2 = ix1 + 64, iy1 + 64
        preview = None
        if f.image_file and os.path.exists(f.image_file):
            preview = self._make_preview(f.image_file, (64, 64))
        if preview:
            self.focus_previews[f.id] = preview
            items["icon"] = self.canvas.create_image(
                (ix1 + ix2) // 2, (iy1 + iy2) // 2, image=preview,
                tags=("focus_" + f.id, "focus"))
        else:
            items["icon"] = self.canvas.create_rectangle(
                ix1, iy1, ix2, iy2, fill="#2a2a2a", outline="#555", width=1,
                tags=("focus_" + f.id, "focus"))
            items["icon_ph"] = self.canvas.create_text(
                (ix1 + ix2) // 2, (iy1 + iy2) // 2, text="◆", fill="#666",
                font=("Arial", 22, "bold"), tags=("focus_" + f.id, "focus"))

        # Заголовок
        title = f.title if f.title else f.id
        if len(title) > 26:
            title = title[:24] + "…"
        items["title"] = self.canvas.create_text(
            x1 + 80, y1 + 18, text=title, fill="white",
            font=("Arial", 11, "bold"), anchor="nw",
            width=x2 - x1 - 88, tags=("focus_" + f.id, "focus"))

        # ID
        id_show = f.id if len(f.id) <= 22 else f.id[:20] + "…"
        items["id"] = self.canvas.create_text(
            x1 + 80, y1 + 52, text=id_show, fill="#aaaaaa",
            font=("Arial", 8), anchor="nw",
            width=x2 - x1 - 88, tags=("focus_" + f.id, "focus"))

        # Cost
        items["cost"] = self.canvas.create_text(
            x2 - 8, y2 - 8, text="★ " + str(f.cost), fill="#ffdd44",
            font=("Arial", 10, "bold"), anchor="se",
            tags=("focus_" + f.id, "focus"))

        self.cv_items[f.id] = items

    def _redraw_connections(self):
        self.canvas.delete("conn")
        for f in self.focuses.values():
            for group in f.prereq_groups:
                valid = [p for p in group if p in self.focuses]
                if not valid:
                    continue
                is_or = len(valid) > 1
                color = "#ffaa44" if is_or else "#88ccff"
                dash = (6, 4) if is_or else None
                for pre_id in valid:
                    p = self.focuses[pre_id]
                    sx = p.x * self.GRID_X + self.GRID_X // 2
                    sy = p.y * self.GRID_Y + self.GRID_Y // 2 + self.FH // 2
                    ex = f.x * self.GRID_X + self.GRID_X // 2
                    ey = f.y * self.GRID_Y + self.GRID_Y // 2 - self.FH // 2
                    if abs(sx - ex) < 2:
                        self.canvas.create_line(sx, sy, ex, ey, fill=color, width=2,
                                                 arrow=tk.LAST, dash=dash, tags="conn")
                    else:
                        my = (sy + ey) / 2
                        self.canvas.create_line(sx, sy, sx, my, fill=color, width=2,
                                                 dash=dash, tags="conn")
                        self.canvas.create_line(sx, my, ex, my, fill=color, width=2,
                                                 dash=dash, tags="conn")
                        self.canvas.create_line(ex, my, ex, ey, fill=color, width=2,
                                                 arrow=tk.LAST, dash=dash, tags="conn")
        self.canvas.tag_lower("conn")
        self.canvas.tag_lower("grid")
        
    def _redraw_all(self):
        for fid in list(self.cv_items.keys()):
            for it in self.cv_items[fid].values():
                self.canvas.delete(it)
        self.cv_items.clear()
        self.focus_previews.clear()
        for f in self.focuses.values():
            self._draw_focus(f)
        self._redraw_connections()

    def _hit_test(self, x, y):
        for fid, items in self.cv_items.items():
            c = self.canvas.coords(items["rect"])
            if c and c[0] <= x <= c[2] and c[1] <= y <= c[3]:
                return fid
        return None

    def _cv_press(self, e):
        x = self.canvas.canvasx(e.x)
        y = self.canvas.canvasy(e.y)
        clicked = self._hit_test(x, y)
        if self.connect_mode:
            if clicked is None:
                if self.connect_src:
                    self._unhighlight(self.connect_src)
                    self.connect_src = None
                    self.set_hint("Соединение отменено.")
                return
            if self.connect_src is None:
                self.connect_src = clicked
                self._highlight(clicked, "yellow")
                self.set_hint("Источник: «" + clicked + "» (ПРЕДПОСЫЛКА). Кликните зависимый фокус.")
            else:
                if clicked != self.connect_src:
                    target = self.focuses[clicked]   # зависимый
                    src_id = self.connect_src        # предпосылка
                    mode = self.connect_logic.get()
                    added = False
                    if mode == "AND":
                        if not any(src_id in g for g in target.prereq_groups):
                            target.prereq_groups.append([src_id])
                            added = True
                    else:  # OR
                        if target.prereq_groups:
                            last = target.prereq_groups[-1]
                            if src_id not in last:
                                last.append(src_id)
                                added = True
                        else:
                            target.prereq_groups.append([src_id])
                            added = True
                    if added:
                        self._redraw_connections()
                        self.status_var.set("Связь [" + mode + "]: " + src_id + " → " + clicked)
                        self.set_hint("Связь создана. Ещё одна или выключите режим.")
                        if self.selected_focus == clicked:
                            self._refresh_prereq_list()
                    else:
                        self.set_hint("Такая связь уже есть.")
                self._unhighlight(self.connect_src)
                self.connect_src = None
            return
        if clicked:
            self.focus_select(clicked)
            f = self.focuses[clicked]
            self.drag = (clicked, x - f.x * self.GRID_X, y - f.y * self.GRID_Y)

    def _cv_drag(self, e):
        if not self.drag or self.connect_mode:
            return
        fid, ox, oy = self.drag
        x = self.canvas.canvasx(e.x)
        y = self.canvas.canvasy(e.y)
        nx = max(0, round((x - ox) / self.GRID_X))
        ny = max(0, round((y - oy) / self.GRID_Y))
        f = self.focuses[fid]
        if f.x != nx or f.y != ny:
            f.x, f.y = nx, ny
            self._draw_focus(f)
            self._redraw_connections()
            if self.selected_focus == fid:
                self.f_x.set(f.x)
                self.f_y.set(f.y)

    def _cv_release(self, e):
        self.drag = None

    def _cv_right(self, e):
        x = self.canvas.canvasx(e.x)
        y = self.canvas.canvasy(e.y)
        fid = self._hit_test(x, y)
        if fid:
            self.focus_select(fid)
            self.focus_delete()

    def _cv_wheel(self, e):
        self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def _highlight(self, fid, color):
        if fid in self.cv_items:
            self.canvas.itemconfig(self.cv_items[fid]["rect"], outline=color, width=3)

    def _unhighlight(self, fid):
        if fid in self.cv_items:
            color = "#ffd700" if fid == self.selected_focus else "#7a7a7a"
            width = 3 if fid == self.selected_focus else 2
            self.canvas.itemconfig(self.cv_items[fid]["rect"], outline=color, width=width)

    # ---------- данные фокусов ----------

    def focus_select(self, fid):
        if fid not in self.focuses:
            return
        self.selected_focus = fid
        f = self.focuses[fid]
        for i in range(self.focus_list.size()):
            if self.focus_list.get(i) == fid:
                self.focus_list.selection_clear(0, tk.END)
                self.focus_list.selection_set(i)
                self.focus_list.see(i)
                break
        self.f_id.set(f.id)
        self.f_title.set(f.title)
        self.f_icon.set(f.icon)
        self.f_cost.set(f.cost)
        self.f_x.set(f.x)
        self.f_y.set(f.y)
        self.f_desc.delete("1.0", tk.END)
        self.f_desc.insert("1.0", f.description)
        self.f_effects.delete("1.0", tk.END)
        self.f_effects.insert("1.0", f.effects)
        self._update_focus_preview()
        self._refresh_prereq_list()
        for other, items in self.cv_items.items():
            color = "#ffd700" if other == fid else "#7a7a7a"
            width = 3 if other == fid else 2
            self.canvas.itemconfig(items["rect"], outline=color, width=width)

    def _refresh_prereq_list(self):
        for item in self.f_prereq.get_children():
            self.f_prereq.delete(item)
        if not self.selected_focus:
            return
        f = self.focuses[self.selected_focus]
        for gi, group in enumerate(f.prereq_groups):
            if not group:
                continue
            logic = "OR" if len(group) > 1 else "AND"
            gid = self.f_prereq.insert("", "end",
                text="Группа #" + str(gi + 1) + " [" + logic + "]",
                open=True, tags=("group", str(gi)))
            for ii, pid in enumerate(group):
                marker = "•" if pid in self.focuses else "⚠"
                self.f_prereq.insert(gid, "end",
                    text="   " + marker + " " + pid,
                    tags=("item", str(gi), str(ii)))

    def prereq_add_group(self):
        if not self.selected_focus:
            return
        fid = simpledialog.askstring("AND-группа",
            "ID фокуса-предпосылки (обязателен):", parent=self.root)
        if not fid:
            return
        fid = fid.strip()
        if fid not in self.focuses:
            messagebox.showerror("Ошибка", "Такого фокуса нет.")
            return
        if fid == self.selected_focus:
            messagebox.showerror("Ошибка", "Фокус не может быть своей предпосылкой.")
            return
        self.focuses[self.selected_focus].prereq_groups.append([fid])
        self._refresh_prereq_list()
        self._redraw_connections()

    def prereq_add_or(self):
        if not self.selected_focus:
            return
        sel = self.f_prereq.selection()
        if not sel:
            messagebox.showinfo("OR", "Выдели группу в дереве, к которой добавить OR.")
            return
        tags = self.f_prereq.item(sel[0], "tags")
        gi = int(tags[1])
        fid = simpledialog.askstring("OR-элемент",
            "ID фокуса (достаточно любого из группы):", parent=self.root)
        if not fid:
            return
        fid = fid.strip()
        if fid not in self.focuses:
            messagebox.showerror("Ошибка", "Такого фокуса нет.")
            return
        if fid == self.selected_focus:
            messagebox.showerror("Ошибка", "Фокус не может быть своей предпосылкой.")
            return
        group = self.focuses[self.selected_focus].prereq_groups[gi]
        if fid in group:
            messagebox.showinfo("OR", "Этот фокус уже в группе.")
            return
        group.append(fid)
        self._refresh_prereq_list()
        self._redraw_connections()

    def prereq_delete(self):
        if not self.selected_focus:
            return
        sel = self.f_prereq.selection()
        if not sel:
            return
        tags = self.f_prereq.item(sel[0], "tags")
        gi = int(tags[1])
        f = self.focuses[self.selected_focus]
        if tags[0] == "group":
            del f.prereq_groups[gi]
        else:
            ii = int(tags[2])
            del f.prereq_groups[gi][ii]
            if not f.prereq_groups[gi]:
                del f.prereq_groups[gi]
        self._refresh_prereq_list()
        self._redraw_connections()
        
    def _refresh_focus_list(self):
        self.focus_list.delete(0, tk.END)
        for fid in sorted(self.focuses):
            marker = " 📷" if self.focuses[fid].image_file else ""
            self.focus_list.insert(tk.END, fid + marker)

    def _on_focus_list_select(self, e):
        sel = self.focus_list.curselection()
        if not sel:
            return
        fid = self.focus_list.get(sel[0]).replace(" 📷", "")
        self.focus_select(fid)
        f = self.focuses[fid]
        self.canvas.xview_moveto(max(0, f.x * self.GRID_X - 400) / 4000)
        self.canvas.yview_moveto(max(0, f.y * self.GRID_Y - 250) / 2600)

    def focus_add(self):
        fid = simpledialog.askstring("Новый фокус",
            "ID фокуса (латиница, цифры, _, начиная с буквы):",
            parent=self.root)
        if not fid:
            return
        fid = fid.strip()
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', fid):
            messagebox.showerror("Ошибка", "Некорректный ID.")
            return
        if fid in self.focuses:
            messagebox.showerror("Ошибка", "ID уже существует.")
            return
        n = len(self.focuses)
        f = Focus(fid)
        f.x = n % 5
        f.y = n // 5
        self.focuses[fid] = f
        self._refresh_focus_list()
        self._draw_focus(f)
        self._redraw_connections()
        self.focus_select(fid)
        self.status_var.set("Добавлен: " + fid)

    def focus_dup(self):
        if not self.selected_focus:
            self.set_hint("Выберите фокус для дублирования.")
            return
        src = self.focuses[self.selected_focus]
        fid = simpledialog.askstring("Дублировать", "ID копии:",
            initialvalue=self.selected_focus + "_copy", parent=self.root)
        if not fid:
            return
        fid = fid.strip()
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', fid):
            messagebox.showerror("Ошибка", "Некорректный ID.")
            return
        if fid in self.focuses:
            messagebox.showerror("Ошибка", "ID уже занят.")
            return
        d = src.to_dict()
        d["id"] = fid
        d["x"] = src.x + 1
        d["prereq_groups"] = []
        new_f = Focus.from_dict(d)
        self.focuses[fid] = new_f
        self._refresh_focus_list()
        self._draw_focus(new_f)
        self._redraw_connections()
        self.focus_select(fid)
        self.status_var.set("Дубликат: " + fid)

    def focus_apply(self):
        if not self.selected_focus:
            self.set_hint("Сначала выберите фокус.")
            return
        f = self.focuses[self.selected_focus]
        new_id = self.f_id.get().strip()
        if new_id and new_id != f.id:
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', new_id):
                messagebox.showerror("Ошибка", "Некорректный ID.")
                return
            if new_id in self.focuses:
                messagebox.showerror("Ошибка", "ID занят.")
                return
            old = f.id
            del self.focuses[old]
            f.id = new_id
            self.focuses[new_id] = f
            for other in self.focuses.values():
                other.prereq_groups = [
                    [new_id if p == old else p for p in g]
                    for g in other.prereq_groups
                ]
            self.selected_focus = new_id
            if f.image_file and f.icon.startswith("GFX_focus_"):
                f.icon = "GFX_focus_" + new_id
                self.f_icon.set(f.icon)
        f.title = self.f_title.get().strip() or f.id
        icon_val = self.f_icon.get().strip()
        if icon_val:
            f.icon = icon_val
            if not f.image_file:
                pass  # стандартная иконка
        try:
            f.cost = int(self.f_cost.get())
        except (ValueError, tk.TclError):
            f.cost = 10
        try:
            f.x = int(self.f_x.get())
        except (ValueError, tk.TclError):
            pass
        try:
            f.y = int(self.f_y.get())
        except (ValueError, tk.TclError):
            pass
        f.description = self.f_desc.get("1.0", tk.END).strip()
        f.effects = self.f_effects.get("1.0", tk.END).strip()
        self._refresh_focus_list()
        self._draw_focus(f)
        self._redraw_connections()
        self.status_var.set("Сохранено: " + f.id)
        self.set_hint("Фокус сохранён. Можно выбрать другой или создать новый.")

    def focus_delete(self):
        if not self.selected_focus:
            self.set_hint("Выберите фокус для удаления.")
            return
        fid = self.selected_focus
        if not messagebox.askyesno("Удаление", "Удалить фокус «" + fid + "»?"):
            return
        del self.focuses[fid]
        for other in self.focuses.values():
            other.prereq_groups = [
                [p for p in g if p != fid] for g in other.prereq_groups
            ]
            other.prereq_groups = [g for g in other.prereq_groups if g]
        if fid in self.cv_items:
            for it in self.cv_items[fid].values():
                self.canvas.delete(it)
            del self.cv_items[fid]
        if fid in self.focus_previews:
            del self.focus_previews[fid]
        self.selected_focus = None
        self._refresh_focus_list()
        self._redraw_connections()
        self.f_id.set("")
        self.f_title.set("")
        self.f_icon.set("")
        self.f_cost.set(10)
        self.f_x.set(0)
        self.f_y.set(0)
        self.f_desc.delete("1.0", tk.END)
        self.f_effects.delete("1.0", tk.END)
        self.f_prereq.delete(0, tk.END)
        self.f_preview_label.config(image="", text="(нет своей картинки)")
        self.status_var.set("Удалён: " + fid)

    def toggle_connect(self):
        self.connect_mode = not self.connect_mode
        if self.connect_mode:
            self.b_connect.config(text="🔗 Соединить (ВКЛ)")
            self.canvas.config(cursor="crosshair")
            self.set_hint("Кликните предпосылку, затем зависимый. Выключите повторно.")
        else:
            self.b_connect.config(text="🔗 Соединить")
            self.canvas.config(cursor="")
            if self.connect_src:
                self._unhighlight(self.connect_src)
                self.connect_src = None
            self.set_hint("Режим соединения выключен.")

    def _append_effect(self, code):
        self.f_effects.insert(tk.END, code + "\n")

    def _copy_effects(self):
        text = self.f_effects.get("1.0", tk.END).strip()
        if not text:
            self.set_hint("Нечего копировать.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set("Код эффектов скопирован в буфер обмена")

    # ===================================================== ИДЕИ

    def _build_idea_tab(self):
        tb = ttk.Frame(self.idea_tab, padding=(6, 4))
        tb.pack(side=tk.TOP, fill=tk.X)
        b_add = ttk.Button(tb, text="＋ Идея", command=self.idea_add)
        b_add.pack(side=tk.LEFT, padx=2)
        b_del = ttk.Button(tb, text="🗑 Удалить", command=self.idea_delete)
        b_del.pack(side=tk.LEFT, padx=2)
        b_dup = ttk.Button(tb, text="📋 Дублировать", command=self.idea_dup)
        b_dup.pack(side=tk.LEFT, padx=2)
        b_save = ttk.Button(tb, text="💾 Применить", command=self.idea_apply)
        b_save.pack(side=tk.RIGHT, padx=2)

        paned = ttk.PanedWindow(self.idea_tab, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)
        left = ttk.Frame(paned, width=280)
        paned.add(left, weight=0)
        ttk.Label(left, text="Список идей", font=("", 10, "bold")).pack(anchor=tk.W, padx=6, pady=(6, 2))
        lw = ttk.Frame(left)
        lw.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.idea_list = tk.Listbox(lw, exportselection=False)
        sb = ttk.Scrollbar(lw, orient=tk.VERTICAL, command=self.idea_list.yview)
        self.idea_list.config(yscrollcommand=sb.set)
        self.idea_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.idea_list.bind("<<ListboxSelect>>", self._on_idea_list_select)

        right = ttk.Frame(paned)
        paned.add(right, weight=1)
        self._build_idea_props(right)

    def _build_idea_props(self, parent):
        ttk.Label(parent, text="Свойства идеи", font=("", 10, "bold")).pack(anchor=tk.W, padx=6, pady=(6, 2))
        nb = ttk.Notebook(parent)
        nb.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        basic = ttk.Frame(nb, padding=8)
        nb.add(basic, text="Основное")
        mods = ttk.Frame(nb, padding=8)
        nb.add(mods, text="Модификаторы")
        conds = ttk.Frame(nb, padding=8)
        nb.add(conds, text="Условия")

        def row(label, var, tip=""):
            r = ttk.Frame(basic); r.pack(fill=tk.X, pady=2)
            ttk.Label(r, text=label, width=16).pack(side=tk.LEFT)
            e = ttk.Entry(r, textvariable=var)
            e.pack(side=tk.LEFT, fill=tk.X, expand=True)
            if tip:
                Tooltip(e, tip)
            return e

        self.i_id = tk.StringVar()
        row("ID:", self.i_id)
        self.i_name = tk.StringVar()
        row("Название:", self.i_name)
        self.i_desc = tk.StringVar()
        row("Описание:", self.i_desc)

        ttk.Label(basic, text="Картинка идеи:", font=("", 9, "bold")).pack(anchor=tk.W, pady=(8, 2))
        r = ttk.Frame(basic); r.pack(fill=tk.X, pady=2)
        ttk.Label(r, text="Стандартная:", width=16).pack(side=tk.LEFT)
        self.i_pic = tk.StringVar()
        ttk.Combobox(r, textvariable=self.i_pic, values=IDEA_PICTURES,
                     state="normal").pack(side=tk.LEFT, fill=tk.X, expand=True)
        r = ttk.Frame(basic); r.pack(fill=tk.X, pady=2)
        b_pick = ttk.Button(r, text="📁 Своя картинка (DDS/PNG)...", command=self.pick_idea_image)
        b_pick.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        Tooltip(b_pick, "Своё изображение для идеи.\n"
                        "Рекомендуется 65×65 .dds или .png.\n"
                        "При экспорте попадёт в gfx/interface/ideas/custom/.")
        b_reset = ttk.Button(r, text="✖ Сброс", command=self.reset_idea_image, width=10)
        b_reset.pack(side=tk.LEFT)

        self.i_preview = tk.Label(basic, text="(нет своей картинки)",
                                  bg="#333", fg="#999", width=10, height=3,
                                  relief=tk.SUNKEN, bd=1)
        self.i_preview.pack(pady=4)

        r = ttk.Frame(basic); r.pack(fill=tk.X, pady=2)
        ttk.Label(r, text="Категория:", width=16).pack(side=tk.LEFT)
        self.i_cat = tk.StringVar(value="country")
        ttk.Combobox(r, textvariable=self.i_cat, values=IDEA_CATEGORIES,
                     state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True)

        r = ttk.Frame(basic); r.pack(fill=tk.X, pady=2)
        ttk.Label(r, text="Стоимость удаления:", width=16).pack(side=tk.LEFT)
        self.i_rc = tk.IntVar(value=0)
        ttk.Spinbox(r, from_=0, to=99999, textvariable=self.i_rc, width=8).pack(side=tk.LEFT)

        # --- модификаторы (категоризированные)
        ttk.Label(mods, text="Быстрые модификаторы:").pack(anchor=tk.W)
        cat_nb = ttk.Notebook(mods)
        cat_nb.pack(fill=tk.X, pady=(2, 6))
        for cat_name, items in IDEA_MODIFIERS.items():
            sub = ttk.Frame(cat_nb, padding=4)
            cat_nb.add(sub, text=cat_name[:6])
            for label, code in items:
                b = ttk.Button(sub, text=label,
                               command=lambda c=code: self.i_modifier.insert(tk.END, c + "\n"))
                b.pack(fill=tk.X, pady=1)
                Tooltip(b, "Вставит: " + code)

        ttk.Label(mods, text="modifier = { ... } (содержимое):").pack(anchor=tk.W)
        self.i_modifier = tk.Text(mods, height=8, wrap=tk.WORD, font=("Consolas", 9))
        self.i_modifier.pack(fill=tk.BOTH, expand=True, pady=2)

        def cond_block(label, tip):
            ttk.Label(conds, text=label).pack(anchor=tk.W, pady=(4, 0))
            t = tk.Text(conds, height=3, wrap=tk.WORD, font=("Consolas", 9))
            t.pack(fill=tk.BOTH, expand=True, pady=2)
            Tooltip(t, tip)
            return t

        self.i_allowed = cond_block("allowed = { ... }",
            "Условие, при котором идею можно взять.\nПо умолчанию: always = yes")
        self.i_available = cond_block("available = { ... }",
            "Условие доступности в списке. Например: has_war = yes")
        self.i_visible = cond_block("visible = { ... }",
            "Условие видимости.\nОбычно: always = yes")

    def pick_idea_image(self):
        if not self.selected_idea:
            self.set_hint("Сначала выберите идею.")
            return
        path = filedialog.askopenfilename(
            title="Выберите картинку для идеи",
            filetypes=[
                ("Изображения HOI4", "*.dds *.png *.tga *.jpg *.jpeg"),
                ("DDS (рекомендуется)", "*.dds"),
                ("PNG", "*.png"),
                ("Все файлы", "*.*"),
            ])
        if not path:
            return
        idea = self.ideas[self.selected_idea]
        idea.image_file = path
        idea.picture = "GFX_idea_" + idea.id
        self.i_pic.set(idea.picture)
        self._update_idea_preview()
        self.status_var.set("Иконка: " + os.path.basename(path))
        self.set_hint("Картинка установлена. Не забудьте «💾 Применить».")

    def reset_idea_image(self):
        if not self.selected_idea:
            return
        idea = self.ideas[self.selected_idea]
        idea.image_file = ""
        idea.picture = IDEA_PICTURES[0]
        self.i_pic.set(idea.picture)
        self._update_idea_preview()
        self.status_var.set("Иконка сброшена")

    def _update_idea_preview(self):
        if not self.selected_idea:
            self.i_preview.config(image="", text="(нет своей картинки)")
            return
        idea = self.ideas[self.selected_idea]
        if not idea.image_file or not os.path.exists(idea.image_file):
            self.i_preview.config(image="", text="(нет своей картинки)")
            return
        photo = self._make_preview(idea.image_file, (65, 65))
        if photo:
            self.i_preview.config(image=photo, text="", width=65, height=65)
            self.i_preview.image = photo
        else:
            self.i_preview.config(image="", text="⚠ " + os.path.basename(idea.image_file),
                                  width=10, height=3)

    def idea_add(self):
        iid = simpledialog.askstring("Новая идея", "ID идеи (латиница):", parent=self.root)
        if not iid:
            return
        iid = iid.strip()
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', iid):
            messagebox.showerror("Ошибка", "Некорректный ID.")
            return
        if iid in self.ideas:
            messagebox.showerror("Ошибка", "ID уже существует.")
            return
        self.ideas[iid] = Idea(iid)
        self._refresh_idea_list()
        self.idea_select(iid)
        self.status_var.set("Добавлена: " + iid)

    def idea_dup(self):
        if not self.selected_idea:
            self.set_hint("Выберите идею для дублирования.")
            return
        src = self.ideas[self.selected_idea]
        iid = simpledialog.askstring("Дублировать", "ID копии:",
            initialvalue=self.selected_idea + "_copy", parent=self.root)
        if not iid:
            return
        iid = iid.strip()
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', iid):
            messagebox.showerror("Ошибка", "Некорректный ID.")
            return
        if iid in self.ideas:
            messagebox.showerror("Ошибка", "ID занят.")
            return
        d = src.to_dict()
        d["id"] = iid
        self.ideas[iid] = Idea.from_dict(d)
        self._refresh_idea_list()
        self.idea_select(iid)
        self.status_var.set("Дубликат: " + iid)

    def idea_delete(self):
        if not self.selected_idea:
            self.set_hint("Выберите идею для удаления.")
            return
        iid = self.selected_idea
        if not messagebox.askyesno("Удаление", "Удалить идею «" + iid + "»?"):
            return
        del self.ideas[iid]
        self.selected_idea = None
        self._refresh_idea_list()
        self._clear_idea_form()
        self.status_var.set("Удалена: " + iid)

    def idea_apply(self):
        if not self.selected_idea:
            self.set_hint("Сначала выберите идею.")
            return
        idea = self.ideas[self.selected_idea]
        new_id = self.i_id.get().strip()
        if new_id and new_id != idea.id:
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', new_id):
                messagebox.showerror("Ошибка", "Некорректный ID.")
                return
            if new_id in self.ideas:
                messagebox.showerror("Ошибка", "ID занят.")
                return
            del self.ideas[idea.id]
            idea.id = new_id
            self.ideas[new_id] = idea
            self.selected_idea = new_id
            if idea.image_file and idea.picture.startswith("GFX_idea_"):
                idea.picture = "GFX_idea_" + new_id
                self.i_pic.set(idea.picture)
        idea.name_text = self.i_name.get().strip() or idea.id
        idea.desc_text = self.i_desc.get().strip()
        pic_val = self.i_pic.get().strip()
        if pic_val:
            idea.picture = pic_val
        idea.category = self.i_cat.get()
        try:
            idea.removal_cost = int(self.i_rc.get())
        except (ValueError, tk.TclError):
            idea.removal_cost = 0
        idea.modifier = self.i_modifier.get("1.0", tk.END).strip()
        idea.allowed = self.i_allowed.get("1.0", tk.END).strip()
        idea.available = self.i_available.get("1.0", tk.END).strip()
        idea.visible = self.i_visible.get("1.0", tk.END).strip()
        self._refresh_idea_list()
        self.status_var.set("Сохранено: " + idea.id)

    def idea_select(self, iid):
        if iid not in self.ideas:
            return
        self.selected_idea = iid
        idea = self.ideas[iid]
        for i in range(self.idea_list.size()):
            entry = self.idea_list.get(i)
            if entry.split("] ", 1)[-1].replace(" 📷", "") == iid:
                self.idea_list.selection_clear(0, tk.END)
                self.idea_list.selection_set(i)
                self.idea_list.see(i)
                break
        self.i_id.set(idea.id)
        self.i_name.set(idea.name_text)
        self.i_desc.set(idea.desc_text)
        self.i_pic.set(idea.picture)
        self.i_cat.set(idea.category)
        self.i_rc.set(idea.removal_cost)
        self.i_modifier.delete("1.0", tk.END)
        self.i_modifier.insert("1.0", idea.modifier)
        self.i_allowed.delete("1.0", tk.END)
        self.i_allowed.insert("1.0", idea.allowed)
        self.i_available.delete("1.0", tk.END)
        self.i_available.insert("1.0", idea.available)
        self.i_visible.delete("1.0", tk.END)
        self.i_visible.insert("1.0", idea.visible)
        self._update_idea_preview()

    def _clear_idea_form(self):
        self.i_id.set("")
        self.i_name.set("")
        self.i_desc.set("")
        self.i_pic.set("")
        self.i_cat.set("country")
        self.i_rc.set(0)
        for t in (self.i_modifier, self.i_allowed, self.i_available, self.i_visible):
            t.delete("1.0", tk.END)
        self.i_preview.config(image="", text="(нет своей картинки)")

    def _refresh_idea_list(self):
        self.idea_list.delete(0, tk.END)
        for iid in sorted(self.ideas):
            idea = self.ideas[iid]
            marker = " 📷" if idea.image_file else ""
            self.idea_list.insert(tk.END, "[" + idea.category + "] " + iid + marker)

    def _on_idea_list_select(self, e):
        sel = self.idea_list.curselection()
        if not sel:
            return
        text = self.idea_list.get(sel[0])
        iid = text.split("] ", 1)[-1].replace(" 📷", "")
        if self.selected_idea and self.selected_idea != iid:
            try:
                self.idea_apply()
            except Exception:
                pass
        self.idea_select(iid)

    # ===================================================== ФАЙЛЫ

    def new_project(self):
        if (self.focuses or self.ideas) and not messagebox.askyesno(
                "Новый проект", "Текущие данные будут потеряны. Продолжить?"):
            return
        self.focuses.clear()
        self.ideas.clear()
        self.selected_focus = None
        self.selected_idea = None
        self.mod_name = "My Mod"
        self.mod_folder = "my_mod"
        self.mod_tag = "GER"
        self.tree_id = "my_focus_tree"
        self.mod_factor = 100
        self._redraw_all()
        self._refresh_focus_list()
        self._refresh_idea_list()
        self._clear_idea_form()
        self.status_var.set("Новый проект создан")

    def save_project(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
            filetypes=[("HOI4 Editor Project", "*.json")])
        if not path:
            return
        data = {
            "mod_name": self.mod_name, "mod_folder": self.mod_folder,
            "mod_tag": self.mod_tag, "tree_id": self.tree_id,
            "mod_factor": self.mod_factor,
            "focuses": {fid: f.to_dict() for fid, f in self.focuses.items()},
            "ideas": {iid: i.to_dict() for iid, i in self.ideas.items()},
        }
        try:
            with open(path, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2)
            self.status_var.set("Сохранено: " + path)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def load_project(self):
        path = filedialog.askopenfilename(filetypes=[("HOI4 Editor Project", "*.json")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            self.mod_name = data.get("mod_name", self.mod_name)
            self.mod_folder = data.get("mod_folder", self.mod_folder)
            self.mod_tag = data.get("mod_tag", self.mod_tag)
            self.tree_id = data.get("tree_id", self.tree_id)
            self.mod_factor = data.get("mod_factor", self.mod_factor)
            self.focuses = {fid: Focus.from_dict(d) for fid, d in data.get("focuses", {}).items()}
            self.ideas = {iid: Idea.from_dict(d) for iid, d in data.get("ideas", {}).items()}
            self.selected_focus = None
            self.selected_idea = None
            self._redraw_all()
            self._refresh_focus_list()
            self._refresh_idea_list()
            self._clear_idea_form()
            self.status_var.set("Загружено: " + path)
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e))

    def mod_settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Настройки мода")
        dlg.geometry("480x310")
        dlg.transient(self.root)
        dlg.grab_set()
        fields = [
            ("Название мода:", "mod_name", self.mod_name),
            ("Имя папки (латиница):", "mod_folder", self.mod_folder),
            ("Тег страны (3 буквы):", "mod_tag", self.mod_tag),
            ("ID дерева фокусов:", "tree_id", self.tree_id),
            ("Приоритет (factor):", "mod_factor", str(self.mod_factor)),
        ]
        vars_ = {}
        for i, (label, key, val) in enumerate(fields):
            ttk.Label(dlg, text=label).grid(row=i, column=0, sticky=tk.W, padx=10, pady=6)
            v = tk.StringVar(value=val)
            vars_[key] = v
            ttk.Entry(dlg, textvariable=v, width=34).grid(row=i, column=1, padx=10, pady=6)

        def save():
            folder = vars_["mod_folder"].get().strip()
            tree = vars_["tree_id"].get().strip()
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', folder):
                messagebox.showerror("Ошибка", "Имя папки — латиница.")
                return
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', tree):
                messagebox.showerror("Ошибка", "ID дерева — латиница.")
                return
            self.mod_name = vars_["mod_name"].get()
            self.mod_folder = folder
            self.mod_tag = vars_["mod_tag"].get().upper()[:3]
            self.tree_id = tree
            try:
                self.mod_factor = int(vars_["mod_factor"].get())
            except ValueError:
                self.mod_factor = 100
            dlg.destroy()
            self.status_var.set("Настройки мода сохранены")
        bf = ttk.Frame(dlg)
        bf.grid(row=len(fields), column=0, columnspan=2, pady=15)
        ttk.Button(bf, text="OK", command=save).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Отмена", command=dlg.destroy).pack(side=tk.LEFT, padx=4)

    def export_mod(self):
        if not (self.focuses or self.ideas):
            self.set_hint("Нечего экспортировать.")
            messagebox.showwarning("Экспорт", "Нечего экспортировать.")
            return
        out_dir = filedialog.askdirectory(title="Выберите папку для экспорта мода")
        if not out_dir:
            return
        mod_dir = os.path.join(out_dir, self.mod_folder)
        if os.path.exists(mod_dir):
            if not messagebox.askyesno("Экспорт",
                    "Папка существует:\n" + mod_dir + "\n\nПерезаписать?"):
                return
            shutil.rmtree(mod_dir)
        try:
            report = self._write_all(out_dir, mod_dir)
            msg = "Мод создан:\n" + mod_dir + "\n\n"
            if report["copied_focus_imgs"] or report["copied_idea_imgs"]:
                msg += "Своих картинок: фокусов = " + str(report["copied_focus_imgs"])
                msg += ", идей = " + str(report["copied_idea_imgs"]) + "\n\n"
            msg += ("Скопируйте папку и .mod-файл в:\n"
                    "Documents/Paradox Interactive/Hearts of Iron IV/mod/\n\n"
                    "Включите мод в лаунчере.")
            messagebox.showinfo("Экспорт завершён", msg)
            self.status_var.set("Экспортировано: " + mod_dir)
        except Exception as e:
            messagebox.showerror("Ошибка экспорта", str(e))

    def _write_all(self, out_dir, mod_dir):
        os.makedirs(mod_dir, exist_ok=True)
        # .mod-файл
        mod_path = os.path.join(out_dir, self.mod_folder + ".mod")
        with open(mod_path, "w", encoding="utf-8") as fp:
            fp.write('name="' + self.mod_name + '"\n')
            fp.write('version="1.0"\n')
            fp.write('supported_version="1.14.*"\n')
            fp.write('path="mod/' + self.mod_folder + '"\n')
            fp.write('tags={ "Fixes" }\n')
        with open(os.path.join(mod_dir, "descriptor.mod"), "w", encoding="utf-8") as fp:
            fp.write('name="' + self.mod_name + '"\n')
            fp.write('version="1.0"\n')
            fp.write('supported_version="1.14.*"\n')
            fp.write('tags={ "Fixes" }\n')

        copied_focus = 0
        copied_idea = 0

        if self.focuses:
            self._write_focus_tree(os.path.join(mod_dir, "common", "national_focus"))
            copied_focus = self._copy_focus_images(mod_dir)
        if self.ideas:
            self._write_ideas(os.path.join(mod_dir, "common", "ideas"))
            copied_idea = self._copy_idea_images(mod_dir)
        self._write_localization(os.path.join(mod_dir, "localisation", "russian"))

        return {"copied_focus_imgs": copied_focus, "copied_idea_imgs": copied_idea}

    def _write_focus_tree(self, focus_dir):
        os.makedirs(focus_dir, exist_ok=True)
        L = []
        L.append("focus_tree = {")
        L.append("    id = " + self.tree_id)
        L.append("    country = {")
        L.append("        factor = 0")
        L.append("        modifier = {")
        L.append("            add = " + str(self.mod_factor))
        L.append("            tag = " + self.mod_tag)
        L.append("        }")
        L.append("    }")
        L.append("    default = no")
        L.append("")
        for f in self.focuses.values():
            L.append("    focus = {")
            L.append("        id = " + f.id)
            L.append("        icon = " + f.icon)
            L.append("        x = " + str(f.x))
            L.append("        y = " + str(f.y))
            L.append("        cost = " + str(f.cost))
            L.append("        ai_will_do = { factor = 1 }")
            for group in f.prereq_groups:
                valid = [p for p in group if p in self.focuses and p != f.id]
                if not valid:
                    continue
                L.append("        prerequisite = {")
                for p in valid:
                    L.append("            focus = " + p)
                L.append("        }")
            L.append("        completion_reward = {")
            if f.effects.strip():
                for line in f.effects.strip().splitlines():
                    L.append("            " + line.strip())
            else:
                L.append("            # эффекты не заданы")
            L.append("        }")
            L.append("    }")
            L.append("")
        L.append("}")
        with open(os.path.join(focus_dir, self.tree_id + ".txt"), "w", encoding="utf-8") as fp:
            fp.write("\n".join(L))

    def _write_ideas(self, ideas_dir):
        os.makedirs(ideas_dir, exist_ok=True)
        by_cat = {}
        for idea in self.ideas.values():
            by_cat.setdefault(idea.category, []).append(idea)
        L = []
        L.append("ideas = {")
        for cat, ideas in by_cat.items():
            L.append("    " + cat + " = {")
            for idea in ideas:
                L.append("        " + idea.id + " = {")
                L.append("            picture = " + idea.picture)
                if idea.modifier.strip():
                    L.append("            modifier = {")
                    for line in idea.modifier.strip().splitlines():
                        L.append("                " + line.strip())
                    L.append("            }")
                if idea.removal_cost:
                    L.append("            removal_cost = " + str(idea.removal_cost))
                for key, val in (("allowed", idea.allowed),
                                 ("available", idea.available),
                                 ("visible", idea.visible)):
                    if val.strip():
                        L.append("            " + key + " = {")
                        for line in val.strip().splitlines():
                            L.append("                " + line.strip())
                        L.append("            }")
                L.append("        }")
            L.append("    }")
        L.append("}")
        with open(os.path.join(ideas_dir, self.mod_folder + "_ideas.txt"), "w", encoding="utf-8") as fp:
            fp.write("\n".join(L))

    def _copy_focus_images(self, mod_dir):
        """Копирует свои картинки фокусов в мод и создаёт .gfx. Возвращает кол-во."""
        gfx_dir = os.path.join(mod_dir, "gfx", "interface", "goals", "custom")
        copied = []
        for f in self.focuses.values():
            if not f.image_file or not os.path.exists(f.image_file):
                continue
            os.makedirs(gfx_dir, exist_ok=True)
            ext = os.path.splitext(f.image_file)[1].lower() or ".dds"
            dest_name = f.id + ext
            dest_path = os.path.join(gfx_dir, dest_name)
            try:
                shutil.copy2(f.image_file, dest_path)
                copied.append((f.icon, "gfx/interface/goals/custom/" + dest_name))
            except Exception:
                pass
        if copied:
            gfx_path = os.path.join(gfx_dir, "custom_focus_icons.gfx")
            with open(gfx_path, "w", encoding="utf-8") as fp:
                fp.write("spriteTypes = {\n")
                for gfx_name, rel_path in copied:
                    fp.write("    spriteType = {\n")
                    fp.write("        name = \"" + gfx_name + "\"\n")
                    fp.write("        texturefile = \"" + rel_path + "\"\n")
                    fp.write("    }\n")
                fp.write("}\n")
        return len(copied)

    def _copy_idea_images(self, mod_dir):
        gfx_dir = os.path.join(mod_dir, "gfx", "interface", "ideas", "custom")
        copied = []
        for idea in self.ideas.values():
            if not idea.image_file or not os.path.exists(idea.image_file):
                continue
            os.makedirs(gfx_dir, exist_ok=True)
            ext = os.path.splitext(idea.image_file)[1].lower() or ".dds"
            dest_name = idea.id + ext
            dest_path = os.path.join(gfx_dir, dest_name)
            try:
                shutil.copy2(idea.image_file, dest_path)
                copied.append((idea.picture, "gfx/interface/ideas/custom/" + dest_name))
            except Exception:
                pass
        if copied:
            gfx_path = os.path.join(gfx_dir, "custom_idea_icons.gfx")
            with open(gfx_path, "w", encoding="utf-8") as fp:
                fp.write("spriteTypes = {\n")
                for gfx_name, rel_path in copied:
                    fp.write("    spriteType = {\n")
                    fp.write("        name = \"" + gfx_name + "\"\n")
                    fp.write("        texturefile = \"" + rel_path + "\"\n")
                    fp.write("    }\n")
                fp.write("}\n")
        return len(copied)

    def _write_localization(self, loc_dir):
        os.makedirs(loc_dir, exist_ok=True)
        with open(os.path.join(loc_dir, self.mod_folder + "_l_russian.yml"),
                  "w", encoding="utf-8-sig") as fp:
            fp.write("l_russian:\n")
            for f in self.focuses.values():
                title = f.title.replace('"', '\\"')
                desc = (f.description or ("Описание фокуса " + f.title)).replace('"', '\\"').replace("\n", " ")
                fp.write(' ' + f.id + ':0 "' + title + '"\n')
                fp.write(' ' + f.id + '_desc:0 "' + desc + '"\n')
            if self.focuses:
                fp.write(' ' + self.tree_id + ':0 "' + self.mod_name + '"\n')
                fp.write(' ' + self.tree_id + '_desc:0 "Дерево фокусов ' + self.mod_name + '"\n')
            for idea in self.ideas.values():
                name = (idea.name_text or idea.id).replace('"', '\\"')
                desc = (idea.desc_text or ("Описание идеи " + idea.id)).replace('"', '\\"').replace("\n", " ")
                fp.write(' ' + idea.id + ':0 "' + name + '"\n')
                fp.write(' ' + idea.id + '_desc:0 "' + desc + '"\n')

    # ===================================================== Справка

    def show_help(self):
        messagebox.showinfo("Как пользоваться",
            "🌳 ФОКУСЫ:\n"
            "1. «＋ Фокус» → введите ID → OK.\n"
            "2. Перетащите фокус мышью. Правый клик — удалить.\n"
            "3. Справа: название, иконка, стоимость, эффекты.\n"
            "4. Своя картинка:\n"
            "   • Вкладка «Основное» → «📁 Своя картинка»\n"
            "   • Рекомендуется 156×108 .dds\n"
            "   • При экспорте попадёт в gfx/interface/goals/custom/\n"
            "   • .gfx генерируется автоматически!\n"
            "5. Быстрые эффекты разбиты по 8 категориям\n"
            "   (Политика / Армия / Пром / Наука / Авиа / Флот / Дипло / Особое).\n"
            "6. «📋 Копировать всё» — код в буфер обмена.\n"
            "7. Связи: «🔗 Соединить» → клик на предпосылку → клик на зависимый.\n\n"
            "💡 ИДЕИ:\n"
            "1. «＋ Идея» → ID → заполнить поля.\n"
            "2. Своя картинка — аналогично фокусам (65×65).\n"
            "3. Категории: country (нацдух), political_advisor, army_chief и др.\n"
            "4. Модификаторы разбиты по категориям.\n\n"
            "📤 ЭКСПОРТ:\n"
            "• Кнопка «📤 Экспорт мода» → выберите папку.\n"
            "• Скопируйте папку и .mod в:\n"
            "  Documents/Paradox Interactive/Hearts of Iron IV/mod/\n"
            "• Включите мод в лаунчере.\n\n"
            "💾 ПРОЕКТ:\n"
            "• Ctrl+S — сохранить в .json\n"
            "• Ctrl+O — открыть сохранённый проект\n"
            "• Ctrl+E — экспорт\n\n"
            "ℹ️ Для предпросмотра .dds-картинок:\n"
            "   pip install Pillow\n"
            "   (без этого превью только для .png, но экспорт работает всегда)")

    def show_about(self):
        messagebox.showinfo("О программе",
            "HOI4 Focus & Idea Editor v2.0\n\n"
            "• Свои картинки для фокусов и идей\n"
            "• Автогенерация .gfx-файлов\n"
            "• Категоризированные эффекты (8 категорий)\n"
            "• Превью иконок в карточках и свойствах\n"
            "• Дублирование фокусов и идей\n\n"
            "Только Python 3 + Tkinter.\n"
            "Опционально: Pillow для превью .dds.")


# ===================================================== Запуск

if __name__ == "__main__":
    root = tk.Tk()
    try:
        style = ttk.Style()
        for name in ("vista", "clam", "default"):
            if name in style.theme_names():
                style.theme_use(name)
                break
    except Exception:
        pass
    app = HOI4Editor(root)
    root.mainloop()