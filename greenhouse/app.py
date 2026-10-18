"""Tkinter desktop dashboard. Sensor values are never invented in live mode."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import json
import secrets
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .core import Store, Simulator, Reading, Irrigation, alerts
from .receiver import Receiver

ROOT = Path(__file__).resolve().parent.parent
BG = '#0b1424'
PANEL = '#15233a'
TEXT = '#edf4fc'
MUTED = '#9dafc8'
COLORS = ['#55baff', '#49d5c4', '#8bdf84', '#ffce64']
METRICS = [('temperature', 'Air temperature', '°C'), ('humidity', 'Air humidity', '%'),
           ('soil_moisture', 'Soil moisture', '%'), ('light_lux', 'Light intensity', 'lux')]


def load_settings():
    path = ROOT/'data'/'settings.json'
    path.parent.mkdir(exist_ok=True)
    defaults = dict(token=secrets.token_urlsafe(24), device='greenhouse-01', host='127.0.0.1',
                    port=8765, stale_seconds=180, temperature_high=38., soil_low=35.)
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(loaded, dict):
                defaults.update({k: v for k, v in loaded.items() if k in defaults})
        except (OSError, ValueError):
            pass
    path.write_text(json.dumps(defaults, indent=2), encoding='utf-8')
    return defaults


class MetricCard(tk.Frame):
    def __init__(self, master, metric, color):
        super().__init__(master, bg=PANEL, highlightthickness=1, highlightbackground='#263750')
        self.metric, self.color = metric, color
        self.rows = []
        self.columnconfigure(0, weight=1)
        tk.Label(self, text=metric[1].upper(), bg=PANEL, fg=MUTED,
                 font=('Segoe UI', 10, 'bold')).grid(row=0, column=0, sticky='w', padx=18, pady=(13, 0))
        self.value = tk.Label(self, text='--', bg=PANEL, fg=color, font=('Segoe UI', 30, 'bold'))
        self.value.grid(row=1, column=0, sticky='w', padx=18)
        self.detail = tk.Label(self, text='Waiting for measurements', bg=PANEL, fg=MUTED,
                               font=('Segoe UI', 9))
        self.detail.grid(row=2, column=0, sticky='w', padx=18)
        self.chart = tk.Canvas(self, height=78, bg=PANEL, highlightthickness=0)
        self.chart.grid(row=3, column=0, sticky='nsew', padx=12, pady=(5, 8))
        self.rowconfigure(3, weight=1)
        self.chart.bind('<Configure>', lambda e: self.draw())

    def update_readings(self, rows):
        self.rows = rows
        if not rows:
            self.value.config(text='-- '+self.metric[2]); self.detail.config(text='No live sample received')
        else:
            values = [r[self.metric[0]] for r in rows]
            current = f'{values[-1]:,.0f}' if self.metric[0] == 'light_lux' else f'{values[-1]:.1f}'
            self.value.config(text=current+' '+self.metric[2])
            self.detail.config(text=f'Window min {min(values):.1f}   |   max {max(values):.1f}')
        self.draw()

    def draw(self):
        c = self.chart; c.delete('all')
        w, height = max(c.winfo_width(), 100), max(c.winfo_height(), 60)
        x0, x1, y0, y1 = 48, w-9, 10, height-20
        for f in (0., .5, 1.):
            y = y0+(y1-y0)*f
            c.create_line(x0, y, x1, y, fill='#243550')
        if not self.rows:
            c.create_text(w/2, height/2, text='Awaiting sensor data', fill=MUTED, font=('Segoe UI', 9)); return
        vals = [r[self.metric[0]] for r in self.rows]
        low, high = min(vals), max(vals)
        pad = max((high-low)*.15, .5 if self.metric[0]!='light_lux' else 5)
        low, high = max(0, low-pad) if self.metric[0]!='temperature' else low-pad, high+pad
        c.create_text(x0-6, y0, text=f'{high:.0f}', fill=MUTED, anchor='e', font=('Segoe UI', 8))
        c.create_text(x0-6, y1, text=f'{low:.0f}', fill=MUTED, anchor='e', font=('Segoe UI', 8))
        points=[]
        times=[datetime.fromisoformat(r['measured_at']).timestamp() for r in self.rows]
        span=max(times[-1]-times[0], .001)
        for t, v in zip(times, vals):
            x=x0+(x1-x0)*(t-times[0])/span
            y=y1-(y1-y0)*(v-low)/max(high-low,.001)
            points.extend((x,y))
        if len(vals)>1:
            c.create_polygon(x0,y1,*points,x1,y1,fill='#1c3548',outline='')
            c.create_line(*points, fill=self.color, width=2)
        c.create_oval(points[-2]-3,points[-1]-3,points[-2]+3,points[-1]+3,fill=self.color,outline='')
        for x, r, anchor in [(x0,self.rows[0],'w'),(x1,self.rows[-1],'e')]:
            t=datetime.fromisoformat(r['measured_at']).astimezone().strftime('%H:%M:%S')
            c.create_text(x,height-7,text=t,anchor=anchor,fill=MUTED,font=('Segoe UI',8))


class Dashboard:
    def __init__(self, root):
        self.root=root; self.settings=load_settings()
        self.store=Store(ROOT/'data'/'greenhouse.sqlite3')
        self.sim=Simulator(); self.irrigation=Irrigation(); self.receiver=None
        self.mode=tk.StringVar(value='demo'); self.paused=tk.BooleanVar(value=False)
        self.scenario=tk.StringVar(value='Normal'); self.auto=tk.BooleanVar(value=True)
        self.last_demo=time.monotonic(); self.last_alert=None; self.current_rows=[]
        self.closing=False
        self.root.title('Greenhouse IoT Lab | Sensor Dashboard')
        self.root.geometry('1150x820'); self.root.minsize(900,700); self.root.configure(bg=BG)
        self.root.columnconfigure(0,weight=1); self.root.rowconfigure(2,weight=1)
        self.style()
        self.build_header(); self.build_tabs()
        self.footer=tk.Label(root,text='',bg=BG,fg=MUTED,anchor='w',font=('Segoe UI',9))
        self.footer.grid(row=3,column=0,sticky='ew',padx=22,pady=(0,10))
        self.store.add(self.sim.sample(advance=False))
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh()

    def style(self):
        style=ttk.Style(); style.theme_use('clam')
        style.configure('.',font=('Segoe UI',10))
        style.configure('TFrame',background=BG)
        style.configure('TNotebook',background=BG,borderwidth=0)
        style.configure('TNotebook.Tab',background=PANEL,foreground=MUTED,padding=(18,9))
        style.map('TNotebook.Tab',background=[('selected','#23435a')],foreground=[('selected',TEXT)])
        style.configure('TButton',background='#24485d',foreground=TEXT,padding=(12,7),borderwidth=0)
        style.map('TButton',background=[('active','#32677b')])
        style.configure('Treeview',background=PANEL,fieldbackground=PANEL,foreground=TEXT,rowheight=28)
        style.configure('Treeview.Heading',background='#243a54',foreground=TEXT)
        style.map('Treeview',background=[('selected','#2a657c')])

    def label(self,parent,text,**kw):
        return tk.Label(parent,text=text,bg=BG,fg=TEXT,font=('Segoe UI',10),**kw)

    def build_header(self):
        head=tk.Frame(self.root,bg=BG);head.grid(row=0,column=0,sticky='ew',padx=22,pady=(16,5))
        head.columnconfigure(0,weight=1)
        self.label(head,'GREENHOUSE / IoT LAB',anchor='w').grid(row=0,column=0,sticky='w')
        tk.Label(head,text='From sensor data to action',bg=BG,fg=TEXT,font=('Segoe UI',23,'bold')).grid(row=1,column=0,sticky='w')
        modes=tk.Frame(head,bg=BG);modes.grid(row=0,column=1,rowspan=2)
        for title,value in [('DEMO','demo'),('LIVE ESP32','real')]:
            tk.Radiobutton(modes,text=title,variable=self.mode,value=value,command=self.change_mode,
                bg=BG,fg=TEXT,selectcolor='#214e60',activebackground=BG,activeforeground=TEXT,
                font=('Segoe UI',10,'bold'),indicatoron=0,padx=13,pady=9).pack(side='left',padx=3)
        self.banner=tk.Label(self.root,text='',bg='#203d51',fg=TEXT,font=('Segoe UI',10),anchor='w',padx=14,pady=8)
        self.banner.grid(row=1,column=0,sticky='ew',padx=22,pady=(4,10))

    def build_tabs(self):
        self.tabs=ttk.Notebook(self.root);self.tabs.grid(row=2,column=0,sticky='nsew',padx=22,pady=(0,10))
        overview=tk.Frame(self.tabs,bg=BG);history=tk.Frame(self.tabs,bg=BG);setup=tk.Frame(self.tabs,bg=BG)
        self.tabs.add(overview,text='Overview');self.tabs.add(history,text='History & events');self.tabs.add(setup,text='IoT connection & settings')
        self.overview=overview
        for i in range(2):overview.columnconfigure(i,weight=1,uniform='cards');overview.rowconfigure(i,weight=1)
        self.cards=[]
        for i,metric in enumerate(METRICS):
            card=MetricCard(overview,metric,COLORS[i]);card.grid(row=i//2,column=i%2,sticky='nsew',padx=(0,8) if i%2==0 else (8,0),pady=(10,0));self.cards.append(card)
        controls=tk.Frame(overview,bg=BG);controls.grid(row=2,column=0,columnspan=2,sticky='ew',pady=(10,4))
        self.label(controls,'Demo scenario:').pack(side='left')
        self.selector=ttk.Combobox(controls,textvariable=self.scenario,values=['Normal','Dry soil','Hot day','Night'],state='readonly',width=12)
        self.selector.pack(side='left',padx=8);self.selector.bind('<<ComboboxSelected>>',self.change_scenario)
        self.pause_button=ttk.Button(controls,text='Pause demo',command=self.pause);self.pause_button.pack(side='left')
        self.auto_button=tk.Checkbutton(controls,text='Auto irrigation (demo)',variable=self.auto,bg=BG,fg=TEXT,
            selectcolor=PANEL,activebackground=BG,activeforeground=TEXT,command=self.auto_changed)
        self.auto_button.pack(side='left',padx=8)
        self.manual_button=ttk.Button(controls,text='Water 10 s (demo)',command=self.manual_water);self.manual_button.pack(side='left',padx=5)
        self.stop_button=ttk.Button(controls,text='Stop',command=self.stop_water);self.stop_button.pack(side='left')
        self.actuator=self.label(overview,'');self.actuator.grid(row=3,column=0,columnspan=2,sticky='w',pady=3)
        self.alert_label=tk.Label(overview,text='',bg='#213b38',fg='#b0efcc',font=('Segoe UI',10,'bold'),anchor='w',padx=12,pady=8,wraplength=1000)
        self.alert_label.grid(row=4,column=0,columnspan=2,sticky='ew',pady=(3,6))
        self.build_history(history);self.build_setup(setup)

    def build_history(self,parent):
        parent.columnconfigure(0,weight=1);parent.rowconfigure(1,weight=1)
        bar=tk.Frame(parent,bg=BG);bar.grid(row=0,column=0,sticky='ew',pady=12)
        self.label(bar,'Latest 120 samples in the selected mode. CSV includes all samples.').pack(side='left')
        ttk.Button(bar,text='Export CSV',command=self.export).pack(side='right')
        cols=('time','source','device','temperature','humidity','soil','lux')
        box=tk.Frame(parent,bg=BG);box.grid(row=1,column=0,sticky='nsew');box.columnconfigure(0,weight=1);box.rowconfigure(0,weight=1)
        self.tree=ttk.Treeview(box,columns=cols,show='headings',height=8)
        for c,name,width in zip(cols,['Measured (local time)','Source','Device','Temp °C','Air %','Soil %','Light lux'],[175,70,130,95,95,95,110]):
            self.tree.heading(c,text=name);self.tree.column(c,width=width,minwidth=65)
        self.tree.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(box,orient='vertical',command=self.tree.yview);scroll.grid(row=0,column=1,sticky='ns');self.tree.configure(yscrollcommand=scroll.set)
        sx=ttk.Scrollbar(box,orient='horizontal',command=self.tree.xview);sx.grid(row=1,column=0,sticky='ew');self.tree.configure(xscrollcommand=sx.set)
        self.label(parent,'RECENT ALERTS & DEMO ACTUATOR EVENTS',anchor='w').grid(row=2,column=0,sticky='w',pady=(14,5))
        self.event_text=tk.Text(parent,height=7,bg=PANEL,fg=MUTED,font=('Consolas',9),wrap='word',relief='flat')
        self.event_text.grid(row=3,column=0,sticky='ew',pady=(0,10));self.event_text.configure(state='disabled')
        self.last_history_key=None

    def build_setup(self,parent):
        parent.columnconfigure(1,weight=1)
        text=('REAL SENSOR MODE | ESP32 → local Wi-Fi → this computer\n'
              'This receiver stores measurements only. It does not operate a physical pump.\n'
              'Loopback (127.0.0.1) is for local tests. Use 0.0.0.0 to listen on the local network.\n'
              'ESP32 URL: http://YOUR_COMPUTER_LAN_IP:8765/api/readings')
        self.label(parent,text,justify='left',anchor='w').grid(row=0,column=0,columnspan=3,sticky='w',pady=15)
        self.host_var=tk.StringVar(value=self.settings['host']);self.port_var=tk.StringVar(value=str(self.settings['port']))
        self.temp_var=tk.StringVar(value=str(self.settings['temperature_high']));self.soil_var=tk.StringVar(value=str(self.settings['soil_low']))
        self.stale_var=tk.StringVar(value=str(self.settings['stale_seconds']))
        for row,(name,var) in enumerate([('Receiver host',self.host_var),('Receiver port',self.port_var),
             ('High temperature alert (°C)',self.temp_var),('Low soil moisture alert (%)',self.soil_var),('Stale after (seconds)',self.stale_var)],1):
            self.label(parent,name,anchor='w').grid(row=row,column=0,sticky='w',padx=(0,18),pady=6)
            ttk.Entry(parent,textvariable=var,width=30).grid(row=row,column=1,sticky='w')
        self.label(parent,'Device ID: greenhouse-01',anchor='w').grid(row=6,column=0,columnspan=2,sticky='w',pady=8)
        self.label(parent,'Local token (paste in secrets.h):',anchor='w').grid(row=7,column=0,sticky='w')
        self.token_var=tk.StringVar(value=self.settings['token'])
        ttk.Entry(parent,textvariable=self.token_var,state='readonly',width=46,show='*').grid(row=7,column=1,sticky='w')
        ttk.Button(parent,text='Copy token',command=self.copy_token).grid(row=7,column=2,padx=6)
        buttons=tk.Frame(parent,bg=BG);buttons.grid(row=8,column=0,columnspan=3,sticky='w',pady=12)
        ttk.Button(buttons,text='Save settings',command=self.save_settings).pack(side='left',padx=(0,7))
        ttk.Button(buttons,text='Start receiver',command=self.start_receiver).pack(side='left',padx=7)
        ttk.Button(buttons,text='Stop receiver',command=self.stop_receiver).pack(side='left',padx=7)
        self.receiver_label=self.label(parent,'Receiver stopped',anchor='w');self.receiver_label.grid(row=9,column=0,columnspan=3,sticky='w',pady=6)
        note=('Demo irrigation uses fixed teaching thresholds: start below 35%, stop at 45%, maximum 20 s.\n'
              'Editable thresholds above affect monitoring alerts, not physical control.\n'
              'No cloud account, paid API or internet connection is needed for demo or local monitoring.\n'
              'Keep the receiver on a trusted private LAN; HTTP is not encrypted. Do not expose it to the internet.\n'
              'Full setup, sensor wiring, calibration and limitations: docs/MANUAL_PT.md.')
        tk.Label(parent,text=note,bg=BG,fg=MUTED,font=('Segoe UI',10),justify='left',wraplength=870).grid(row=10,column=0,columnspan=3,sticky='w',pady=15)

    def change_mode(self):
        self.irrigation.stop();self.last_alert=None;self.last_history_key=None
        live=self.mode.get()=='real'
        self.selector.configure(state='disabled' if live else 'readonly')
        for widget in [self.pause_button,self.auto_button,self.manual_button,self.stop_button]:widget.configure(state='disabled' if live else 'normal')
        self.render()

    def change_scenario(self,event=None):
        if self.mode.get()!='demo':return
        self.irrigation.stop();self.irrigation.locked=False
        self.sim.set_scenario(self.scenario.get());self.paused.set(False);self.pause_button.configure(text='Pause demo')
        self.store.add(self.sim.sample(advance=False));self.store.event('demo','Scenario: '+self.scenario.get());self.last_demo=time.monotonic();self.render()

    def pause(self):
        self.paused.set(not self.paused.get());self.irrigation.stop()
        self.pause_button.configure(text='Resume demo' if self.paused.get() else 'Pause demo')
        self.store.event('demo','Demo paused' if self.paused.get() else 'Demo resumed')

    def auto_changed(self):
        self.irrigation.automatic=self.auto.get()
        if not self.auto.get():self.irrigation.stop()

    def manual_water(self):
        if self.mode.get()!='demo':return
        if self.paused.get():messagebox.showinfo('Paused','Resume the demo before watering.');return
        self.irrigation.start(duration=10);self.store.event('demo','Manual simulated irrigation started: maximum 10 s')

    def stop_water(self):
        self.auto.set(False);self.irrigation.automatic=False;self.irrigation.stop()
        self.store.event('demo','Simulation stopped by user; automatic mode disabled')

    def save_settings(self):
        try:
            port=int(self.port_var.get());temp=float(self.temp_var.get());soil=float(self.soil_var.get());stale=int(self.stale_var.get())
            if not (1<=port<=65535 and -40<=temp<=80 and 0<=soil<=100 and 10<=stale<=86400):raise ValueError()
            host=self.host_var.get().strip()
            if host not in ('127.0.0.1','0.0.0.0'):raise ValueError()
        except ValueError:
            messagebox.showerror('Settings','Use host 127.0.0.1 or 0.0.0.0, valid port, temperature -40..80, soil 0..100 and stale 10..86400.');return False
        if self.receiver and (host!=self.settings['host'] or port!=self.settings['port']):
            messagebox.showinfo('Receiver','Stop the receiver before changing host or port.');return False
        self.settings.update(host=host,port=port,temperature_high=temp,soil_low=soil,stale_seconds=stale)
        (ROOT/'data'/'settings.json').write_text(json.dumps(self.settings,indent=2),encoding='utf-8')
        return True

    def copy_token(self):
        self.root.clipboard_clear();self.root.clipboard_append(self.settings['token'])
        messagebox.showinfo('Token','Token copied. Paste it into your local secrets.h file.')

    def start_receiver(self):
        if self.receiver:return
        if not self.save_settings():return
        receiver=Receiver(self.store,self.settings['token'],self.settings['host'],self.settings['port'])
        try:receiver.start()
        except (OSError,ValueError) as exc:
            messagebox.showerror('Receiver',f'Could not start: {exc}');return
        self.receiver=receiver
        self.receiver_label.configure(text=f'Listening on {receiver.host}:{receiver.port} | POST /api/readings')

    def stop_receiver(self):
        if self.receiver:self.receiver.stop();self.receiver=None
        self.receiver_label.configure(text='Receiver stopped')

    def export(self):
        path=filedialog.asksaveasfilename(title='Export selected source',defaultextension='.csv',
              initialfile=f'greenhouse_{self.mode.get()}.csv',filetypes=[('CSV','*.csv')])
        if path:
            try:self.store.export(self.mode.get(),path)
            except OSError as exc:messagebox.showerror('Export',str(exc));return
            messagebox.showinfo('Export','CSV saved with all samples from the selected source.')

    def refresh(self):
        if self.closing:return
        try:
            if self.mode.get()=='demo':
                latest=self.store.recent('demo',1)
                fresh=bool(latest) and not self.paused.get() and Reading(**{k:latest[-1][k] for k in Reading.__dataclass_fields__}).age()<10
                msg=self.irrigation.update(self.sim.values[2],fresh=fresh)
                # A pause is already logged by the pause button, so avoid repeated stale events.
                if msg and fresh:self.store.event('demo',msg)
                if not self.paused.get() and time.monotonic()-self.last_demo>=2:
                    self.store.add(self.sim.sample(irrigating=self.irrigation.active));self.last_demo=time.monotonic()
            self.render()
        except Exception as exc:
            self.footer.configure(text=f'Local application error: {exc}')
        self.root.after(1000,self.refresh)

    def render(self):
        source=self.mode.get();rows=self.store.recent(source,120);self.current_rows=rows
        reading=Reading(**{k:rows[-1][k] for k in Reading.__dataclass_fields__}) if rows else None
        for card in self.cards:card.update_readings(rows)
        stale=reading is not None and reading.age()>self.settings['stale_seconds']
        if source=='demo':
            self.banner.configure(text='DEMONSTRATION • Synthetic sensor readings • No physical device is connected',bg='#203d51')
            state='ON' if self.irrigation.active else 'OFF'
            lock=' | time limit lock: reset scenario or reach 45% soil' if self.irrigation.locked else ''
            self.actuator.configure(text=f'Simulated valve: {state} | Demo sample: every 2 s'+lock)
        else:
            state='NO DATA' if not reading else ('STALE' if stale else 'RECEIVING')
            self.banner.configure(text=f'LIVE ESP32 • {state} • Real measurements only • Device greenhouse-01',bg='#57402b' if stale or not reading else '#16483e')
            self.actuator.configure(text='Monitoring only | Physical irrigation is not connected or controlled by this software')
        messages=alerts(reading,self.settings['stale_seconds'],self.settings['temperature_high'],self.settings['soil_low'])
        if source=='demo' and self.paused.get():messages=['DEMO PAUSED - readings are frozen']
        alert=' | '.join(messages)
        warning=not messages[0].startswith('All ')
        self.alert_label.configure(text=alert,bg='#4b352e' if warning else '#213b38',fg='#ffdbaf' if warning else '#b0efcc')
        if alert!=self.last_alert:
            self.store.event(source,alert);self.last_alert=alert
        key=(source,rows[-1]['id'] if rows else None,len(rows))
        if key!=self.last_history_key:
            self.tree.delete(*self.tree.get_children())
            for r in reversed(rows):
                timestamp=datetime.fromisoformat(r['measured_at']).astimezone().strftime('%Y-%m-%d %H:%M:%S')
                self.tree.insert('', 'end',values=(timestamp,r['source'],r['device_id'],f"{r['temperature']:.1f}",f"{r['humidity']:.1f}",f"{r['soil_moisture']:.1f}",f"{r['light_lux']:.0f}"))
            self.last_history_key=key
        self.event_text.configure(state='normal');self.event_text.delete('1.0','end')
        for event in self.store.events(source):
            t=datetime.fromisoformat(event['created_at']).astimezone().strftime('%H:%M:%S')
            self.event_text.insert('end',f"{t}  {event['message']}\n")
        self.event_text.configure(state='disabled')
        last='none' if not reading else datetime.fromisoformat(reading.measured_at).astimezone().strftime('%d/%m %H:%M:%S')
        age='' if not reading else f' | Sample age: {reading.age():.0f} s'
        self.footer.configure(text=f'SQLite history | Source: {source} | Samples: {self.store.count(source):,} | Last measured: {last}'+age)

    def close(self):
        self.closing=True;self.irrigation.stop()
        if self.receiver:self.receiver.stop()
        self.root.destroy()


def main():
    root=tk.Tk()
    Dashboard(root)
    root.mainloop()
