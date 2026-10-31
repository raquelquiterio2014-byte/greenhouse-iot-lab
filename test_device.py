"""Send synthetic samples to the isolated HTTP TEST source, not real history."""
import argparse,time
from greenhouse.config import DATA_DIR,load_settings
from greenhouse.device_client import DeviceClient,Outbox


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration',type=float,default=60)
    parser.add_argument('--offline-first',type=float,default=0,help='Initial seconds with simulated link loss')
    args=parser.parse_args()
    if args.duration<=0 or args.offline_first<0:parser.error('Use duration > 0 and offline-first >= 0')
    cfg=load_settings();client=DeviceClient(f"http://127.0.0.1:{cfg['port']}/api/test/readings",cfg['token'],Outbox(DATA_DIR/'test_outbox.sqlite3'))
    start=time.monotonic();last_print=-5
    print('SYNTHETIC HTTP TEST ONLY. Start the receiver before running this script.')
    try:
        while time.monotonic()-start<args.duration:
            elapsed=time.monotonic()-start;client.offline=elapsed<args.offline_first;client.step()
            if elapsed-last_print>=5:print(client.snapshot());last_print=elapsed
            time.sleep(.2)
    except KeyboardInterrupt:pass
    print('Final:',client.snapshot())


if __name__=='__main__':main()
