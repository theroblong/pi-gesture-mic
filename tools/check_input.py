"""Create and close Wayland devices without emitting any input; installer preflight."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop_input import UInputDriver

if __name__ == '__main__':
    driver = UInputDriver(size=(1920,1080))
    driver.close()
    print('Wayland input ready: virtual pointer and keyboard creation passed (no input sent).')
