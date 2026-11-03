"""Connection diagnostics and isolated synthetic device controls."""
import json
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from .config import DATA_DIR
from .connectivity import summarize
from .device_client import DeviceClient,Outbox


class ConnectionPanel:
    def __init__(self,parent,app):
        self.app=app;self.client=None
        self.offline=tk.BooleanVar(value=False);self.paused=tk.BooleanVar(value=False)
        parent.columnconfigure(0,weight=1);parent.rowconfigure(3,weight=1)
        title=tk.Label(parent,text='CONNECTIVITY LAB | Test transport before connecting hardware',bg='#0b1424',fg='#edf4fc',
                       font=('Segoe UI',13,'bold'),anchor='w')
        title.grid(row=0,column=0,sticky='ew',pady=(14,8))
        note=('HTTP TEST sends synthetic values through a real local HTTP request. It NEVER fills LIVE ESP32 history.\n'
              'Physical installation / firmware validation: PENDING. This build does not operate a pump or valve.')
        tk.Label(parent,text=note,bg='#0b1424',fg='#ffce64',justify='left',anchor='w').grid(row=1,column=0,sticky='w',pady=8)
        controls=tk.Frame(parent,bg='#0b1424');controls.grid(row=2,column=0,sticky='ew',pady=8)
        ttk.Button(controls,text='Start test device',command=self.start).grid(row=0,column=0,padx=(0,6),pady=5)
        ttk.Button(controls,text='Stop test device',command=self.stop).grid(row=0,column=1,padx=6,pady=5)
        ttk.Button(controls,text='Start receiver',command=app.start_receiver).grid(row=0,column=2,padx=6,pady=5)
        ttk.Button(controls,text='Stop receiver',command=app.stop_receiver).grid(row=0,column=3,padx=6,pady=5)
        for col,text,var in [(0,'Pause test link (keep sampling)',self.offline),(2,'Pause test sampling (keep heartbeat)',self.paused)]:
            tk.Checkbutton(controls,text=text,variable=var,command=self.flags,bg='#0b1424',fg='#edf4fc',
                selectcolor='#15233a',activebackground='#0b1424',activeforeground='#edf4fc').grid(row=1,column=col,columnspan=2,sticky='w',pady=5)
        self.details=tk.Text(parent,height=15,bg='#15233a',fg='#edf4fc',font=('Consolas',10),wrap='word',relief='flat',padx=12,pady=10)
        self.details.grid(row=3,column=0,sticky='nsew',pady=8)
        actions=tk.Frame(parent,bg='#0b1424');actions.grid(row=4,column=0,sticky='w',pady=8)
        ttk.Button(actions,text='Show HTTP TEST dashboard',command=self.show_test).pack(side='left',padx=(0,10))
        ttk.Button(actions,text='Export connection report',command=self.export).pack(side='left')
        tk.Label(parent,text='Persistent TEST queue: 32 samples maximum. Pause link → queue grows → resume → retry and acknowledgement.\n'
            'Fresh device contact is independent of fresh measurements. A heartbeat does not replace a sensor reading.',
            bg='#0b1424',fg='#9dafc8',justify='left',wraplength=850).grid(row=5,column=0,sticky='w',pady=10)

    def flags(self):
        if self.client:self.client.offline=self.offline.get();self.client.pause_sampling=self.paused.get()

    def start(self):
        if self.client and self.client.snapshot()['running']:return
        if not self.app.receiver:self.app.start_receiver()
        if not self.app.receiver:return
        try:
            self.client=DeviceClient(f'http://127.0.0.1:{self.app.receiver.port}/api/test/readings',self.app.settings['token'],
                                     Outbox(DATA_DIR/'test_outbox.sqlite3'))
            self.flags();self.client.start();self.app.mode.set('test');self.app.change_mode()
        except (OSError,ValueError) as exc:messagebox.showerror('HTTP test',str(exc))

    def stop(self):
        if self.client:self.client.stop()

    def show_test(self):
        self.app.mode.set('test');self.app.change_mode();self.app.tabs.select(0)

    def report(self):
        return dict(version='4.0.0',receiver_running=self.app.receiver is not None,hardware_validation='PENDING',
            real=summarize(self.app.store,'real',self.app.settings['stale_seconds']),
            test=summarize(self.app.store,'test',self.app.settings['stale_seconds']),
            synthetic_client=self.client.snapshot() if self.client else None)

    def refresh(self):
        report=self.report();lines=[]
        lines.append('RECEIVER: '+('LISTENING' if report['receiver_running'] else 'STOPPED'))
        for source,title in [('test','HTTP TEST (synthetic)'),('real','LIVE ESP32 (physical)')]:
            item=report[source];transport=item['transport'];counts=item['counts']
            lines.extend(['',title,
                f"  Device contact: {item['contact_state']} | Measurements: {item['measurement_state']}",
                f"  Contact age: {self.age(item['contact_age_seconds'])} | Sample age: {self.age(item['measurement_age_seconds'])}",
                f"  Stored: {item['stored_samples']} | New accepted: {counts.get('accepted',0)} | Duplicates: {counts.get('duplicate',0)}",
                f"  Rejected: {counts.get('rejected',0)} | ID conflicts: {counts.get('conflict',0)} | Auth failures: {counts.get('unauthorized',0)}",
                f"  Device queue: {transport.get('queue_depth','--')} | Device dropped: {transport.get('dropped_samples','--')}",
                f"  Sensor heartbeat: {item['sensor_status']} | Latest status: {item['last_device_status'] or '--'} | Quality: {item['latest_quality'] or '--'}"])
        client=report['synthetic_client']
        if client:lines.extend(['','LOCAL SYNTHETIC SENDER',json.dumps(client,indent=2)])
        self.details.configure(state='normal');self.details.delete('1.0','end');self.details.insert('1.0','\n'.join(lines));self.details.configure(state='disabled')

    @staticmethod
    def age(value):return '--' if value is None else f'{value:.0f} s'

    def export(self):
        path=filedialog.asksaveasfilename(defaultextension='.json',initialfile='greenhouse_v3_connection_report.json',filetypes=[('JSON','*.json')])
        if path:
            try:
                with open(path,'w',encoding='utf-8') as f:json.dump(self.report(),f,indent=2,allow_nan=False)
            except OSError as exc:messagebox.showerror('Export',str(exc));return
            messagebox.showinfo('Report','Connection report saved. Hardware validation remains pending.')
