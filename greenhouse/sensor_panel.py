"""Scrollable sensor specification and calibration editor (English UI)."""
from dataclasses import replace
import tkinter as tk
from tkinter import ttk, messagebox
from .sensors import SENSORS, Calibration, ideal_adc_voltage


class SensorPanel:
    def __init__(self,parent,registry,store):
        self.registry,self.store=registry,store
        outer=ttk.Frame(parent);outer.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(outer,bg='#0b1424',highlightthickness=0)
        scroll=ttk.Scrollbar(outer,orient='vertical',command=self.canvas.yview)
        scroll.pack(side='right',fill='y');self.canvas.pack(side='left',fill='both',expand=True)
        self.canvas.configure(yscrollcommand=scroll.set)
        self.body=tk.Frame(self.canvas,bg='#0b1424');window=self.canvas.create_window((0,0),window=self.body,anchor='nw')
        self.body.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(window,width=e.width))
        self.body.columnconfigure(1,weight=1)
        self.label('SENSORS: SELECT BY QUANTITY, INTERFACE AND ENVIRONMENT',0,bold=True)
        self.choice=tk.StringVar(value=SENSORS[0]['quantity'])
        box=ttk.Combobox(self.body,textvariable=self.choice,state='readonly',width=45,
                        values=[s['quantity'] for s in SENSORS])
        box.grid(row=1,column=0,columnspan=2,sticky='w',padx=12,pady=7);box.bind('<<ComboboxSelected>>',self.show_spec)
        self.spec=tk.Text(self.body,height=12,wrap='word',bg='#15233a',fg='#edf4fc',font=('Segoe UI',10),relief='flat',padx=10,pady=8)
        self.spec.grid(row=2,column=0,columnspan=3,sticky='ew',padx=12,pady=5)
        self.show_spec()
        self.label('LIVE CALIBRATION | Applies to NEW V2 real samples only',3,bold=True)
        cal=registry.current
        self.fields={}
        fields=[('dry_raw','Dry reference (ADC counts)',cal.dry_raw),('wet_raw','Wet reference (ADC counts)',cal.wet_raw),
                ('temperature_offset','Temperature correction (°C)',cal.temperature_offset),
                ('humidity_offset','Humidity correction (points RH)',cal.humidity_offset),
                ('reference','Probe ID / substrate / reference / operator',cal.reference)]
        for row,(key,label,value) in enumerate(fields,4):
            self.label(label,row)
            v=tk.StringVar(value=str(value));self.fields[key]=v
            ttk.Entry(self.body,textvariable=v,width=30 if key=='reference' else 24).grid(row=row,column=1,columnspan=2,sticky='ew',padx=12,pady=5)
        self.confirm=tk.BooleanVar(value=cal.confirmed)
        tk.Checkbutton(self.body,text='Dry/wet references were measured on this installed probe and substrate',
            variable=self.confirm,bg='#0b1424',fg='#edf4fc',selectcolor='#15233a',activebackground='#0b1424',
            activeforeground='#edf4fc').grid(row=9,column=0,columnspan=3,sticky='w',padx=12,pady=6)
        buttons=tk.Frame(self.body,bg='#0b1424');buttons.grid(row=10,column=0,columnspan=3,sticky='w',padx=12,pady=8)
        ttk.Button(buttons,text='Preview latest real raw sample',command=self.preview).pack(side='left',padx=(0,10))
        ttk.Button(buttons,text='Save calibration revision',command=self.save).pack(side='left')
        self.revision=tk.Label(self.body,text='Current revision: '+cal.revision,bg='#0b1424',fg='#49d5c4',anchor='w')
        self.revision.grid(row=11,column=0,columnspan=3,sticky='w',padx=12,pady=5)
        self.result=tk.Label(self.body,text='Example endpoints are UNCONFIRMED. Live soil card remains unavailable until calibrated.',
            wraplength=820,justify='left',bg='#0b1424',fg='#ffce64')
        self.result.grid(row=12,column=0,columnspan=3,sticky='w',padx=12,pady=10)
        self.label('ADC counts are not volts or soil %. Ideal 0..3.3 V / 12-bit model is a teaching approximation.',13)
        self.label('soil_mv is the mean of separate analogReadMilliVolts() conversions on the ESP32, not the ideal formula.',14)
        self.label('Demo uses a separate SYNTHETIC calibration. Saving live settings never recalculates stored history.',15)
        self.label('Saturation / out-of-calibration values are flagged; a number of decimals is not measurement accuracy.',16)
        self.label('ACTUATOR SPECIFICATION (not a physical driver in this version)',17,bold=True)
        self.label('Irrigation: relay interface + normally closed 12 V valve are a future design, with separate power.',18)
        self.label('Relay logic level, coil supply, load/inrush, flyback protection and failure state require component verification.',19)
        self.label('Only simulated irrigation runs here. No GPIO/relay command is sent to the ESP32.',20)

    def label(self,text,row,bold=False):
        widget=tk.Label(self.body,text=text,bg='#0b1424',fg='#edf4fc' if bold else '#9dafc8',
            font=('Segoe UI',10,'bold' if bold else 'normal'),wraplength=820,justify='left',anchor='w')
        widget.grid(row=row,column=0,columnspan=3 if row not in range(4,9) else 1,sticky='w',padx=12,pady=(10 if bold else 5,4))

    def show_spec(self,event=None):
        item=next(s for s in SENSORS if s['quantity']==self.choice.get())
        text='\n'.join(f'{k.upper()}: {v}' for k,v in item.items())
        self.spec.configure(state='normal');self.spec.delete('1.0','end');self.spec.insert('1.0',text);self.spec.configure(state='disabled')

    def build_calibration(self):
        return Calibration(dry_raw=float(self.fields['dry_raw'].get()),wet_raw=float(self.fields['wet_raw'].get()),
            temperature_offset=float(self.fields['temperature_offset'].get()),humidity_offset=float(self.fields['humidity_offset'].get()),
            confirmed=self.confirm.get(),reference=self.fields['reference'].get()).validate()

    def preview(self):
        try:
            cal=self.build_calibration();rows=self.store.recent('real',1)
            if not rows or rows[-1]['soil_raw'] is None:
                self.result.configure(text='No V2 real ADC sample yet. Connect the V2 firmware; DEMO references are not hardware calibration.');return
            row=rows[-1];raw=row['soil_raw'];bounded,unbounded,flags=cal.soil_index(raw)
            text=(f"Latest stored real raw: {raw:.1f} counts | reported voltage {row['soil_mv']:.1f} mV | "
                  f'preview index {bounded:.1f}% relative | before clamp {unbounded:.1f}% | '+(';'.join(flags) or 'OK'))
            self.result.configure(text=text)
        except ValueError as exc:messagebox.showerror('Calibration',str(exc))

    def save(self):
        try:cal=self.registry.save(self.build_calibration())
        except (ValueError,OSError) as exc:messagebox.showerror('Calibration',str(exc));return
        self.revision.configure(text='Current revision: '+cal.revision+' | '+cal.updated_at)
        self.result.configure(text='Saved. Changes apply when the NEXT real V2 sample arrives. Previous records keep their own calibration snapshot.')
        self.store.event('real','Calibration revision saved: '+cal.revision)
