
from sys import stderr
from typing import List

import argparse
from pathlib import Path
import multiprocessing as mp

from interpolate import MidiInterpolator

argument_parser = argparse.ArgumentParser(description='')

argument_parser.add_argument('--midi-folder', type=Path, default='datasets/midi/', help="Folder containing the midi files.")
argument_parser.add_argument('--save-folder', type=Path, default='output/', help="Folder to save generated transitions.")
args = argument_parser.parse_args()

args.save_folder.mkdir(parents=True, exist_ok=True)

def read_midis(midi_folder: Path) -> List[Path]:
    filenames = []
    for ext in ('*.mid', '*.midi'):
        filenames.extend(midi_folder.glob(ext))

    return filenames

def main() -> int:
    try:
        midis = read_midis(args.midi_folder)
        for midi1 in midis:
            for midi2 in midis:
                MidiInterpolator(files=[midi1, midi2], length=8, outfile=args.save_folder / f'{midi1.stem}_{midi2.stem}.mid').create_infilling()

    except KeyboardInterrupt:
        print('Aborted manually.', file=stderr)
        return 1

    except Exception as e:
        print('Aborted.', e, file=stderr)
        return 1

    return 0 #success

if __name__ == "__main__":
    main()