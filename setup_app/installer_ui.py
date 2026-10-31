"""Resizable, DPI-aware presentation for the local OKDEV installer.

Filesystem validation and installation stay in setup.py. This module owns
only the window, user input and thread-to-UI progress handoff.
"""
from __future__ import annotations

import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk

COLORS = dict(bg='#0b1019', surface='#131c2a', raised='#1b2738', line='#2b3a50',
              text='#edf2fa', muted='#a6b5ca', accent='#c0a7ff', mint='#81e4cd',
              danger='#ffb2bd', on_accent='#211637')


class InstallerWindow:
    def __init__(self, version, paths, validate, install, icon=None, *, smoke=False, scale=None):
        self.window = tk.Tk()
        self.validate = validate
        self.install = install
        self.busy = False
        self.installed = None
        self.messages = queue.Queue()
        self.controls = []
        self.entries = []
        self._poll_id = None
        self._layout_id = None
        self._closed = False
        self._detail_window = None
        self._full_detail = ''
        self.version = version
        w, c = self.window, COLORS
        if smoke:
            w.withdraw()
        if scale is not None:
            w.tk.call('tk', 'scaling', (96 / 72) * scale)
        factor = max(.8, float(w.tk.call('tk', 'scaling')) / (96 / 72))
        self.factor = factor
        width = min(round(820 * factor), w.winfo_screenwidth() - 60)
        height = min(round(730 * factor), w.winfo_screenheight() - 80)
        w.geometry(f'{width}x{height}')
        w.minsize(min(width, round(660 * factor)), min(height, round(560 * factor)))
        w.title(f'OKDEV {version} • Kurulum')
        w.configure(background=c['bg'])
        if icon and Path(icon).is_file():
            w.iconbitmap(str(icon))
        self._style()
        w.columnconfigure(0, weight=1)
        w.rowconfigure(1, weight=1)

        header = ttk.Frame(w, padding=(28, 22, 28, 18))
        header.grid(row=0, column=0, sticky='ew')
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text='OKDEV', style='Brand.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(header, text=f'YEREL KURULUM  /  {version}', style='Caption.TLabel').grid(row=0, column=1, sticky='e')
        ttk.Label(header, text='Oyun alanını hazırla.', style='Heading.TLabel').grid(row=1, column=0, columnspan=2, sticky='w', pady=(10, 4))
        self.intro = ttk.Label(header, text='İlk kurulumunu yap veya mevcut OKDEV klasörünü güncelle. Ayarların ve eski kurulumun yedeği korunur.', style='Muted.TLabel', wraplength=700)
        self.intro.grid(row=2, column=0, columnspan=2, sticky='ew')

        body = ttk.Frame(w, padding=(28, 0, 18, 0))
        body.grid(row=1, column=0, sticky='nsew')
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(body, background=c['bg'], borderwidth=0, highlightthickness=0, takefocus=False)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.scrollbar = ttk.Scrollbar(body, orient='vertical', command=self.canvas.yview)
        self.scrollbar.grid(row=0, column=1, sticky='ns', padx=(8, 0))
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.content = ttk.Frame(self.canvas)
        self.content.columnconfigure(0, weight=1)
        self.content_id = self.canvas.create_window(0, 0, anchor='nw', window=self.content)
        card = tk.Frame(self.content, background=c['surface'], highlightbackground=c['line'], highlightthickness=1)
        card.grid(row=0, column=0, sticky='ew', pady=(0, 16))
        card.columnconfigure(0, weight=1)
        inner = ttk.Frame(card, style='Card.TFrame', padding=20)
        inner.grid(row=0, column=0, sticky='ew')
        inner.columnconfigure(0, weight=1)
        self.values = [tk.StringVar(value=str(path)) for path in paths]
        self.values[0].set('')
        specs = (
            ('01  League of Legends', 'Oyunun kurulu olduğu League of Legends veya Game klasörü.'),
            ('02  Kurulum konumu', 'Güncellemek için mevcut OKDEV klasörünü seç.'),
        )
        self.path_descriptions = []
        for index, ((title, description), variable) in enumerate(zip(specs, self.values[1:]), start=1):
            row = (index - 1) * 3
            ttk.Label(inner, text=title, style='CardHeading.TLabel').grid(row=row, column=0, columnspan=2, sticky='w', pady=(0 if index == 0 else 18, 4))
            note = ttk.Label(inner, text=description, style='CardMuted.TLabel', wraplength=630)
            note.grid(row=row + 1, column=0, columnspan=2, sticky='ew', pady=(0, 8))
            self.path_descriptions.append(note)
            entry = ttk.Entry(inner, textvariable=variable, font=('Segoe UI', 10))
            entry.grid(row=row + 2, column=0, sticky='ew', padx=(0, 10))
            browse = ttk.Button(inner, text='Klasör seç', command=lambda i=index: self.browse(i))
            browse.grid(row=row + 2, column=1, sticky='ew')
            entry.bind('<FocusIn>', lambda event: self.reveal(event.widget))
            browse.bind('<FocusIn>', lambda event: self.reveal(event.widget))
            self.entries.append(entry)
            self.controls.extend((entry, browse))
        self.desktop = tk.BooleanVar(value=True)
        check = ttk.Checkbutton(self.content, text='Masaüstüne OKDEV kısayolu ekle', variable=self.desktop)
        check.grid(row=1, column=0, sticky='w', pady=(0, 10))
        self.controls.append(check)
        check.bind('<FocusIn>', lambda event: self.reveal(event.widget))

        self.footer = ttk.Frame(w, padding=(28, 16, 28, 20))
        self.footer.grid(row=2, column=0, sticky='ew')
        self.footer.columnconfigure(0, weight=1)
        self.status_title = tk.StringVar(value='Kuruluma hazır')
        self.status = tk.StringVar(value='LoL skin bileşeni ilk açılışta resmî kaynaktan otomatik hazırlanır. Ayrı dosya seçmen gerekmez.')
        self.status_heading = ttk.Label(self.footer, textvariable=self.status_title, style='Status.TLabel')
        self.status_heading.grid(row=0, column=0, columnspan=2, sticky='w')
        self.status_label = ttk.Label(self.footer, textvariable=self.status, style='Muted.TLabel', wraplength=700)
        self.status_label.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(4, 10))
        self.details_action = ttk.Button(self.footer, text='Ayrıntıları göster', command=self.show_details)
        self.details_action.grid(row=2, column=0, sticky='w', pady=(0, 10))
        self.details_action.grid_remove()
        self.progress = ttk.Progressbar(self.footer, mode='indeterminate')
        self.progress.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(0, 14))
        self.progress.grid_remove()
        self.cancel = ttk.Button(self.footer, text='Vazgeç', command=self.close)
        self.cancel.grid(row=4, column=0, sticky='w')
        self.action = ttk.Button(self.footer, text='Kur / Güncelle', style='Accent.TButton', command=self.start)
        self.action.grid(row=4, column=1, sticky='e')
        self.license_label = ttk.Label(self.footer, text='OKDEV  •  Açık kaynak bileşenlerin lisansları pakete dahildir.', style='Caption.TLabel', wraplength=700)
        self.license_label.grid(row=5, column=0, columnspan=2, sticky='w', pady=(16, 0))
        self.canvas.bind('<Configure>', self.layout)
        self.content.bind('<Configure>', self.layout)
        w.bind('<Configure>', self._schedule_layout)
        w.bind('<MouseWheel>', self.wheel, add='+')
        w.bind('<Escape>', lambda _: self.close())
        w.protocol('WM_DELETE_WINDOW', self.close)
        self._poll_id = w.after(80, self.poll)
        w.update_idletasks()
        self.layout()
        w.update_idletasks()

    def _style(self):
        c = COLORS
        style = ttk.Style(self.window)
        style.theme_use('clam')
        style.configure('TFrame', background=c['bg'])
        style.configure('Card.TFrame', background=c['surface'])
        style.configure('TLabel', background=c['bg'], foreground=c['text'], font=('Segoe UI', 10))
        style.configure('Brand.TLabel', font=('Segoe UI', 23, 'bold'), foreground=c['accent'])
        style.configure('Heading.TLabel', font=('Segoe UI', 18, 'bold'))
        style.configure('Caption.TLabel', font=('Segoe UI', 9), foreground=c['muted'])
        style.configure('Muted.TLabel', foreground=c['muted'])
        style.configure('Status.TLabel', foreground=c['mint'], font=('Segoe UI', 10, 'bold'))
        style.configure('CardHeading.TLabel', background=c['surface'], font=('Segoe UI', 10, 'bold'))
        style.configure('CardMuted.TLabel', background=c['surface'], foreground=c['muted'], font=('Segoe UI', 9))
        style.configure('TButton', font=('Segoe UI', 10), padding=(15, 9), background=c['raised'], foreground=c['text'], bordercolor=c['line'], lightcolor=c['line'], darkcolor=c['line'], focuscolor=c['accent'])
        style.map('TButton', background=[('active', '#2b2543'), ('disabled', c['surface'])], foreground=[('disabled', '#6b7b91')])
        style.configure('Accent.TButton', background=c['accent'], foreground=c['on_accent'], bordercolor=c['accent'], lightcolor=c['accent'], darkcolor=c['accent'])
        style.map('Accent.TButton', background=[('active', '#d1bfff'), ('disabled', '#63547e')], foreground=[('disabled', '#292433')])
        style.configure('TEntry', fieldbackground='#0f1724', foreground=c['text'], insertcolor=c['accent'], padding=8, bordercolor=c['line'], lightcolor=c['line'], darkcolor=c['line'])
        style.map('TEntry', bordercolor=[('focus', c['accent'])], fieldbackground=[('disabled', c['raised'])], foreground=[('disabled', c['muted'])])
        style.configure('TCheckbutton', background=c['bg'], foreground=c['text'], font=('Segoe UI', 10), focuscolor=c['accent'])
        style.map('TCheckbutton', background=[('active', c['bg'])], foreground=[('disabled', c['muted'])])
        style.configure('Horizontal.TProgressbar', background=c['accent'], troughcolor=c['raised'], bordercolor=c['raised'])
        style.configure('Vertical.TScrollbar', background=c['raised'], troughcolor=c['bg'], bordercolor=c['bg'], arrowcolor=c['muted'])

    def _schedule_layout(self, event):
        if event.widget is self.window and self._layout_id is None:
            self._layout_id = self.window.after_idle(self.layout)

    def layout(self, _event=None):
        if self._closed:
            return
        if self._layout_id is not None:
            self.window.after_cancel(self._layout_id)
        self._layout_id = None
        width = max(160, self.canvas.winfo_width())
        self.canvas.itemconfigure(self.content_id, width=width)
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        wrap = max(200, self.window.winfo_width() - 80)
        self.intro.configure(wraplength=wrap)
        self.status_label.configure(wraplength=wrap)
        self.license_label.configure(wraplength=wrap)
        for label in self.path_descriptions:
            label.configure(wraplength=max(160, width - 46))

    def reveal(self, widget):
        self.window.update_idletasks()
        extent = max(1, self.content.winfo_height())
        top = widget.winfo_rooty() - self.content.winfo_rooty()
        bottom = top + widget.winfo_height()
        current = self.canvas.yview()[0] * extent
        height = self.canvas.winfo_height()
        if top < current:
            self.canvas.yview_moveto(max(0, top - 10) / extent)
        elif bottom > current + height:
            self.canvas.yview_moveto(max(0, bottom + 10 - height) / extent)

    def wheel(self, event):
        if self.content.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(-int(event.delta / 120), 'units')

    def browse(self, index):
        if self.busy:
            return
        selected = filedialog.askdirectory(parent=self.window, title=('Patcher kaynağı', 'League of Legends klasörü', 'OKDEV kurulum konumu')[index], mustexist=True)
        if selected:
            path = Path(selected)
            if index == 2 and not (path / 'okdev-install.json').is_file() and path.name.lower() != 'okdev':
                path /= 'OKDEV'
            self.values[index].set(str(path))
            self.entries[index].focus_set()

    def feedback(self, title, detail, *, error=False):
        self.status_title.set(title)
        self._full_detail = str(detail)
        compact = ' '.join(self._full_detail.split())
        self.status.set(compact if len(compact) <= 180 else compact[:177].rstrip() + '…')
        if len(compact) > 180:
            self.details_action.grid()
        else:
            self.details_action.grid_remove()
        self.status_heading.configure(foreground=COLORS['danger'] if error else COLORS['mint'])
        if self._layout_id is None:
            self._layout_id = self.window.after_idle(self.layout)

    def show_details(self):
        if self._detail_window and self._detail_window.winfo_exists():
            self._detail_window.lift()
            return
        dialog = self._detail_window = tk.Toplevel(self.window)
        dialog.title('OKDEV • İşlem ayrıntıları')
        dialog.transient(self.window)
        dialog.configure(background=COLORS['bg'])
        dialog.geometry(f'{min(round(640 * self.factor), self.window.winfo_screenwidth() - 80)}x{min(round(320 * self.factor), self.window.winfo_screenheight() - 100)}')
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        ttk.Label(dialog, text=self.status_title.get(), style='CardHeading.TLabel', padding=16).grid(row=0, column=0, columnspan=2, sticky='ew')
        detail = tk.Text(dialog, wrap='word', background=COLORS['surface'], foreground=COLORS['text'],
                         selectbackground='#554776', selectforeground=COLORS['text'], font=('Segoe UI', 10),
                         borderwidth=0, highlightthickness=0, padx=16, pady=12)
        detail.grid(row=1, column=0, sticky='nsew', padx=(16, 0), pady=12)
        scroll = ttk.Scrollbar(dialog, command=detail.yview)
        scroll.grid(row=1, column=1, sticky='ns', padx=(0, 16), pady=12)
        detail.configure(yscrollcommand=scroll.set)
        detail.insert('1.0', self._full_detail)
        detail.configure(state='disabled')
        def close_detail():
            dialog.destroy()
            self._detail_window = None
            self.details_action.focus_set()
        ttk.Button(dialog, text='Kapat', command=close_detail).grid(row=2, column=0, columnspan=2, sticky='e', padx=16, pady=(0, 16))
        dialog.protocol('WM_DELETE_WINDOW', close_detail)
        dialog.bind('<Escape>', lambda _: close_detail())
        dialog.grab_set()
        detail.focus_set()

    def open_installed_folder(self):
        try:
            os.startfile(self.installed)
        except OSError as error:
            self.feedback('Klasör açılamadı', f'Kurulum tamamlandı. Klasörü Dosya Gezgini ile açabilirsin: {self.installed}\n{error}', error=True)

    def start(self):
        if self.busy or self.installed:
            return
        try:
            args = self.validate(*(value.get().strip() for value in self.values))
        except (ValueError, OSError) as error:
            self.feedback('Konumları kontrol et', error, error=True)
            return
        self.busy = True
        for control in self.controls + [self.action, self.cancel]:
            control.configure(state='disabled')
        self.feedback('Kurulum sürüyor', 'Dosyalar hazırlanıyor. İşlem bu pencereden takip edilebilir.')
        self.progress.grid()
        self.progress.start(12)
        shortcut = self.desktop.get()

        def work():
            try:
                result = self.install(*args, make_shortcut=shortcut, progress=lambda text: self.messages.put(('progress', text)))
                self.messages.put(('done', result))
            except Exception as error:
                self.messages.put(('error', str(error)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        if self._closed:
            return
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == 'progress':
                    self.feedback('Kurulum sürüyor', value)
                    continue
                self.busy = False
                self.progress.stop()
                self.progress.grid_remove()
                self.cancel.configure(state='normal')
                if kind == 'done':
                    self.installed, warning = value
                    self.feedback('Kurulum tamamlandı', warning or 'OKDEV hazır. Uygulamayı kurulum klasöründen veya masaüstü kısayolundan açabilirsin.')
                    self.cancel.configure(text='Bitir')
                    self.action.configure(text='OKDEV klasörünü aç', state='normal', command=self.open_installed_folder)
                else:
                    for control in self.controls + [self.action]:
                        control.configure(state='normal')
                    self.feedback('Kurulum tamamlanamadı', value, error=True)
        except queue.Empty:
            pass
        self._poll_id = self.window.after(80, self.poll)

    def geometry(self):
        self.window.update_idletasks()
        self.layout()
        self.window.update_idletasks()
        return {'width': self.window.winfo_width(), 'height': self.window.winfo_height(),
                'content_width': self.window.winfo_reqwidth(), 'content_height': self.window.winfo_reqheight(),
                'body_viewport': self.canvas.winfo_height(), 'body_scroll_height': self.content.winfo_height(),
                'body_width': self.canvas.winfo_width(), 'footer_bottom': self.footer.winfo_y() + self.footer.winfo_height(),
                'scale': round(self.factor, 3)}

    def close(self):
        if self.busy:
            self.feedback('Kurulum sürüyor', 'Dosyalar yazılırken pencere kapatılmaz. İşlem tamamlanınca Bitir düğmesini kullanabilirsin.')
            return
        self._closed = True
        for timer in (self._poll_id, self._layout_id):
            if timer is not None:
                try:
                    self.window.after_cancel(timer)
                except tk.TclError:
                    pass
        self.window.destroy()


def run(version, paths, validate, install, icon=None, *, smoke=False):
    ui = InstallerWindow(version, paths, validate, install, icon, smoke=smoke)
    if smoke:
        geometry = ui.geometry()
        assert geometry['footer_bottom'] <= geometry['height'], 'Installer actions exceed the viewport'
        assert geometry['body_viewport'] >= 100, 'Installer paths have no usable scroll viewport'
        ui.close()
        return geometry
    ui.window.mainloop()
