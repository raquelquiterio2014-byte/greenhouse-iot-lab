"""Sensor specifications and traceable transformations for Unit 3."""
from dataclasses import dataclass, asdict, replace
from datetime import datetime, timezone
from pathlib import Path
import json
import math
import threading
import uuid

BH1750_MAX_RAW = 65535
BH1750_FACTOR = 1.2  # H-resolution, MTreg=69, documented nominal conversion.
BH1750_MAX_LUX = BH1750_MAX_RAW / BH1750_FACTOR

SENSORS = [
    dict(model='DHT22 / AM2302',quantity='Air temperature',unit='°C',interface='Digital proprietary; GPIO 4',
         range='-40..80 °C',accuracy='±0.5 °C; resolution 0.1 °C',period='Minimum 2 s; live sampling 60 s',
         supply='3.3 V in this build; sensor rating 3.3..5.5 V',
         placement='At representative canopy height, in a ventilated white radiation shield. Adjust height as plants grow; avoid roof heat, motors, sunlight and spray.',
         calibration='One-point offset against a suitable reference; never immerse a DHT22.',
         reason='Measures air, not liquid or soil temperature.'),
    dict(model='DHT22 / AM2302',quantity='Air relative humidity',unit='% RH',interface='Same DHT22 as temperature',
         range='0..100% RH',accuracy='Typical ±2 percentage points RH, maximum ±5 under datasheet conditions; resolution 0.1',
         period='Minimum 2 s; live sampling 60 s',supply='Same module',
         placement='Ventilated shield near canopy; avoid condensation and direct water exposure.',
         calibration='Optional reference offset; temperature and humidity corrections are separate.',
         reason='A digital output does not guarantee field accuracy; verify the actual module.'),
    dict(model='DFRobot SEN0193',quantity='Relative soil moisture index',unit='% relative (not VWC)',
         interface='Analog AO -> GPIO 34 / ADC1, 12 bits, 11 dB attenuation',
         range='ADC 0..4095; calibrated relative scale 0..100',accuracy='No universal ±% accuracy or VWC claim',
         period='Mean of 10 ADC samples; one live bundle per 60 s',
         supply='Supply 3.3 V here; manufacturer 3.3..5.5 V, output 0..3.0 V',
         placement='Sensing blade in representative active root zone, firm substrate contact. Keep top electronics dry; depth depends on roots, pot and probe length.',
         calibration='Dry and wet references for THIS probe, substrate, power and ADC settings. Example 3000/1200 is unconfirmed.',
         reason='Capacitive sensing avoids exposed resistive electrodes; does not make the whole PCB waterproof.'),
    dict(model='ROHM BH1750FVI module',quantity='Illuminance',unit='lux (not PAR/PPFD)',
         interface='I2C 0x23; SDA 21 / SCL 22',
         range='16-bit raw; H mode MTreg 69: raw / 1.2, maximum 54,612.5 lux',
         accuracy='Nominal ±20% under datasheet test conditions; output step 1/1.2 lux in this mode',
         period='H-resolution conversion up to 180 ms; live read every 60 s',
         supply='3.3 V module compatible; bare IC 2.4..3.6 V',
         placement='Horizontal, facing upward just above canopy, no structural shadows. Any protective optical window changes response and must be checked.',
         calibration='Fixed H-resolution mode and MTreg=69. Raw 65535 is flagged as saturation, not accepted as reliable sunlight data.',
         reason='Unlike an LDR it provides a defined lux conversion. High sunlight may exceed this mode; a PAR sensor is a different future requirement.'),
]


def finite(value, name):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    return float(value)


def two_point(raw, l1, v1, l2, v2):
    raw,l1,v1,l2,v2=[finite(v,'Calibration value') for v in (raw,l1,v1,l2,v2)]
    if l1 == l2:raise ValueError('Calibration endpoints must differ')
    return v1+(raw-l1)*(v2-v1)/(l2-l1)


def mean_adc(samples):
    if not samples:raise ValueError('ADC sample list is empty')
    values=[finite(x,'ADC sample') for x in samples]
    if any(not 0<=x<=4095 for x in values):raise ValueError('ADC sample outside 0..4095')
    return sum(values)/len(values)


def ideal_adc_voltage(raw):
    """Teaching model only. NOT ESP32 calibrated voltage."""
    raw=finite(raw,'ADC')
    if not 0<=raw<=4095:raise ValueError('ADC outside 0..4095')
    return raw/4095*3.3


@dataclass(frozen=True)
class Calibration:
    revision: str = 'example-unconfirmed'
    dry_raw: float = 3000.
    wet_raw: float = 1200.
    temperature_offset: float = 0.
    humidity_offset: float = 0.
    confirmed: bool = False
    reference: str = ''
    updated_at: str = ''

    def validate(self):
        for name in ('dry_raw','wet_raw','temperature_offset','humidity_offset'):
            finite(getattr(self,name),name)
        if not (1<=self.dry_raw<=4094 and 1<=self.wet_raw<=4094):
            raise ValueError('Use endpoints inside the ADC rails (1..4094)')
        if abs(self.dry_raw-self.wet_raw)<50:
            raise ValueError('Endpoint separation must be at least 50 ADC counts for this prototype')
        if not -5<=self.temperature_offset<=5 or not -10<=self.humidity_offset<=10:
            raise ValueError('Offset limits: temperature ±5 °C; humidity ±10 points RH')
        if type(self.confirmed) is not bool:raise ValueError('confirmed must be boolean')
        if not isinstance(self.reference,str) or len(self.reference)>500:
            raise ValueError('Reference must contain up to 500 characters')
        if self.confirmed and not self.reference.strip():
            raise ValueError('Record probe, substrate and references before confirming')
        return self

    def soil_index(self,raw):
        self.validate()
        value=two_point(raw,self.dry_raw,0,self.wet_raw,100)
        flags=[]
        if not self.confirmed:flags.append('CALIBRATION_REQUIRED')
        if raw<=0 or raw>=4095:flags.append('SOIL_ADC_AT_RAIL')
        if not 0<=value<=100:flags.append('SOIL_OUTSIDE_CALIBRATION')
        return max(0,min(100,value)),value,flags

    def snapshot(self):return json.dumps(asdict(self),sort_keys=True)


class CalibrationRegistry:
    def __init__(self,path):
        self.path=Path(path);self.lock=threading.Lock()
        if self.path.exists():
            self.current=Calibration(**json.loads(self.path.read_text(encoding='utf-8'))).validate()
        else:self.current=Calibration()

    def save(self,calibration):
        calibration.validate()
        new=replace(calibration,revision=uuid.uuid4().hex[:12],updated_at=datetime.now(timezone.utc).isoformat())
        with self.lock:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            tmp=self.path.with_suffix('.tmp')
            tmp.write_text(new.snapshot(),encoding='utf-8');tmp.replace(self.path)
            self.current=new
        return new


DEMO_CALIBRATION=Calibration(revision='demo-3000-1200',confirmed=True,
    reference='SYNTHETIC references only: course example 3000 dry / 1200 wet')


def soil_usable(reading):
    return reading.schema_version==2 and not any(x in reading.quality for x in
        ('CALIBRATION_REQUIRED','SOIL_ADC_AT_RAIL','SOIL_OUTSIDE_CALIBRATION','LEGACY'))
