"""Optional headless receiver; use main.py for the desktop application."""
import argparse
import time
from greenhouse.config import DATA_DIR,load_settings
from greenhouse.core import Store
from greenhouse.sensors import CalibrationRegistry
from greenhouse.receiver import Receiver


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lan',action='store_true',help='Listen on 0.0.0.0 for private LAN devices')
    args=parser.parse_args();settings=load_settings()
    receiver=Receiver(Store(DATA_DIR/'greenhouse.sqlite3'),settings['token'],
        '0.0.0.0' if args.lan else '127.0.0.1',settings['port'],calibration_registry=CalibrationRegistry(DATA_DIR/'calibration.json'))
    receiver.start()
    print(f'Greenhouse V3 receiver: {receiver.host}:{receiver.port}. Ctrl+C to stop.')
    print('Configuration and token: data/settings.json (never publish this file).')
    try:
        while True:time.sleep(.5)
    except KeyboardInterrupt:pass
    finally:receiver.stop()


if __name__=='__main__':main()
