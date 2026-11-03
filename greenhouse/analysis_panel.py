"""Explicit, asynchronous analysis requests; no model calls from refresh loops."""
import json,os,queue,threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from .analysis import AnalysisService,synthetic_case,format_report
from .llm_gateway import GeminiGateway
from .connectivity import summarize

CASES=['Current selected source','Normal example','Rising heat','Dry soil','Temperature spike',
       'Stale readings','Uncalibrated soil','Saturated light']


class AnalysisPanel:
    def __init__(self,parent,app):
        self.app=app;self.service=AnalysisService(app.store);self.last_report=None;self.busy=False
        self.results=queue.Queue();self.case=tk.StringVar(value=CASES[0]);self.use_gemini=tk.BooleanVar(value=False)
        self.model=tk.StringVar(value=os.environ.get('GEMINI_MODEL','gemini-2.5-flash'))
        self.key=tk.StringVar(value='')
        parent.columnconfigure(0,weight=1);parent.rowconfigure(3,weight=1)
        tk.Label(parent,text='AI ANALYSIS | Measurement quality first',bg='#0b1424',fg='#edf4fc',
            font=('Segoe UI',13,'bold'),anchor='w').grid(row=0,column=0,sticky='ew',pady=(12,5))
        options=tk.Frame(parent,bg='#0b1424');options.grid(row=1,column=0,sticky='ew')
        for col,text in [(0,'Input'),(2,'Gemini model')]:
            tk.Label(options,text=text,bg='#0b1424',fg='#edf4fc').grid(row=0,column=col,padx=5,sticky='w')
        ttk.Combobox(options,textvariable=self.case,values=CASES,state='readonly',width=26).grid(row=0,column=1,padx=5,pady=5)
        ttk.Entry(options,textvariable=self.model,width=24).grid(row=0,column=3,padx=5)
        tk.Label(options,text='Session key (or GEMINI_API_KEY environment variable)',bg='#0b1424',fg='#9dafc8').grid(row=1,column=0,columnspan=2,sticky='w',pady=4)
        ttk.Entry(options,textvariable=self.key,show='*',width=32).grid(row=1,column=2,columnspan=2,padx=5,sticky='w')
        tk.Checkbutton(options,text='Send the selected aggregate summary to Gemini (optional external API)',variable=self.use_gemini,
            bg='#0b1424',fg='#edf4fc',selectcolor='#15233a',activebackground='#0b1424',activeforeground='#edf4fc').grid(row=2,column=0,columnspan=4,sticky='w',pady=6)
        bar=tk.Frame(parent,bg='#0b1424');bar.grid(row=2,column=0,sticky='ew',pady=5)
        self.run_button=ttk.Button(bar,text='Analyze snapshot',command=self.run);self.run_button.pack(side='left',padx=(0,10))
        ttk.Button(bar,text='Export JSON',command=lambda:self.export('json')).pack(side='left',padx=5)
        ttk.Button(bar,text='Export text',command=lambda:self.export('txt')).pack(side='left',padx=5)
        ttk.Button(bar,text='Recent run history',command=self.history).pack(side='left',padx=5)
        self.status=tk.Label(bar,text='Local analysis ready | Hardware validation pending',bg='#0b1424',fg='#ffce64')
        self.status.pack(side='left',padx=10)
        box=tk.Frame(parent,bg='#0b1424');box.grid(row=3,column=0,sticky='nsew');box.columnconfigure(0,weight=1);box.rowconfigure(0,weight=1)
        self.text=tk.Text(box,bg='#15233a',fg='#edf4fc',font=('Consolas',10),wrap='word',relief='flat',padx=12,pady=10)
        self.text.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(box,orient='vertical',command=self.text.yview);scroll.grid(row=0,column=1,sticky='ns');self.text.configure(yscrollcommand=scroll.set)
        self.show('Select a synthetic example to start immediately, or Current selected source to use the source selected at the top.\n\n'
            'Minimum: five valid samples spanning 20 seconds, within a 30-minute window.\n'
            'Stale, uncalibrated, saturated, inconsistent or insufficient readings block analysis and model calls.\n\n'
            'Local screening uses descriptive trends and median/MAD jump checks. It is not a trained AI model.\n'
            'Optional Gemini selects an evidence-review order and existing verification templates. It cannot change measurements, authorize actions or control equipment.\n\n'
            'The model name is editable because API availability depends on your account. Errors use a clearly labelled local fallback. Keys are kept in session memory only.')
        tk.Label(parent,text='No crop diagnosis, forecast, field validation or physical actuation. Gemini is called only after an explicit click and opt-in.',
            bg='#0b1424',fg='#9dafc8',wraplength=900,justify='left').grid(row=4,column=0,sticky='w',pady=8)

    def show(self,text):
        self.text.configure(state='normal');self.text.delete('1.0','end');self.text.insert('1.0',text);self.text.configure(state='disabled')

    def run(self):
        if self.busy:return
        name=self.case.get();source=self.app.mode.get() if name==CASES[0] else 'demo'
        key=self.key.get().strip() or None;model=self.model.get().strip();use=self.use_gemini.get()
        settings=dict(stale_seconds=self.app.settings['stale_seconds'],temperature_high=self.app.settings['temperature_high'],soil_low=self.app.settings['soil_low'])
        self.busy=True;self.run_button.configure(state='disabled');self.status.configure(text='Capturing and analyzing snapshot...')
        def worker():
            try:
                rows=None if name==CASES[0] else synthetic_case('Normal' if name=='Normal example' else name)
                status=summarize(self.app.store,source)['sensor_status'] if source in ('test','real') else 'UNKNOWN'
                gateway=GeminiGateway(key=key,model=model) if use else None
                report=self.service.run(source,rows=rows,gateway=gateway,use_gemini=use,sensor_status=status,
                    input_kind='stored_history' if rows is None else 'synthetic_case: '+name,**settings)
                self.results.put(('ok',report))
            except Exception as exc:self.results.put(('error',type(exc).__name__))
        threading.Thread(target=worker,daemon=True,name='greenhouse-analysis').start()
        self.app.root.after(100,self.poll)

    def poll(self):
        if self.app.closing:return
        try:kind,value=self.results.get_nowait()
        except queue.Empty:self.app.root.after(100,self.poll);return
        self.busy=False;self.run_button.configure(state='normal')
        if kind=='error':
            self.status.configure(text='Analysis unavailable: '+value);self.show('Could not complete analysis. Check input settings and local storage. No action authorized.');return
        self.last_report=value;self.status.configure(text=value['status']+' | '+value['ai']['engine'])
        self.show(format_report(value))

    def export(self,kind):
        if not self.last_report:messagebox.showinfo('Report','Analyze a snapshot first.');return
        path=filedialog.asksaveasfilename(defaultextension='.'+kind,initialfile='greenhouse_v4_analysis.'+kind,
            filetypes=[(kind.upper(),'*.'+kind)])
        if path:
            try:
                with open(path,'w',encoding='utf-8') as stream:
                    stream.write(json.dumps(self.last_report,indent=2,allow_nan=False) if kind=='json' else format_report(self.last_report))
            except OSError as exc:messagebox.showerror('Export',str(exc))

    def history(self):
        rows=self.service.history(self.app.mode.get())
        window=tk.Toplevel(self.app.root);window.title('Analysis run history — selected source')
        text=tk.Text(window,width=105,height=18,bg='#15233a',fg='#edf4fc',wrap='word');text.pack(fill='both',expand=True)
        text.insert('1.0','\n'.join(f"{r['created_at']} | {r['status']} | {r['engine']} | {r['run_id']}" for r in rows) or 'No analysis runs for the selected source yet.')
        text.configure(state='disabled')
