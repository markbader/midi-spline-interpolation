from typing import List
from scipy import interpolate
import argparse
from pathlib import Path

from miditoolkit.midi import parser as mid_parser
from miditoolkit.midi import containers as ct

def read_midi(filepath: Path) -> List:
    # load midi file
    mido_obj = mid_parser.MidiFile(filepath)

    notes = mido_obj.instruments[0].notes
    melody = notes[:]
    melody.sort(key=lambda x: x.start)

    # reduce to basic melody (take note with lowest pitch)
    index = 0
    while index + 1 < len(melody):
        if melody[index].start == melody[index + 1].start:
            if melody[index].pitch < melody[index + 1].pitch:
                del melody[index + 1]
            else:
                del melody[index]
            continue
        index += 1

    return melody, notes

def write_midi(filepath: Path, notes):
    # create an empty file
    mido_obj = mid_parser.MidiFile()

    # create an  instrument
    track = ct.Instrument(program=0, is_drum=False, name='piano track')
    mido_obj.instruments = [track]

    mido_obj.instruments[0].notes = notes

    # write to file
    mido_obj.dump(filepath)


def f(x: float, x_points, y_points):

    tck = interpolate.splrep(x_points, y_points)
    return interpolate.splev(x, tck)

def main(begin: Path, end: Path, length: int, outfile: Path) -> None:
    begin_melody, begin_notes = read_midi(begin)
    end_melody, end_notes = read_midi(end)

    result = []

    x_points = []
    y_points = []

    begin_avg_note = 0
    for note in begin_melody:
        begin_avg_note += int(note.end - note.start)
        x_points.append(int(note.start))
        y_points.append(int(note.pitch))
    begin_avg_note //= len(begin_melody)

    end_of_begin = begin_melody[-1].end
    begin_of_end = end_of_begin + length*460*4

    end_avg_note = 0
    for note in end_melody:
        end_avg_note += int(note.end - note.start)
        x_points.append(int(note.start) + begin_of_end)
        y_points.append(int(note.pitch))
    end_avg_note //= len(end_melody)

    # Add begin to result
    result.extend(begin_notes)

    # Create transition
    position = end_of_begin
    while True:
        rel_position = (position - end_of_begin) / (begin_of_end - end_of_begin)
        note_length = rel_position * end_avg_note + (1 - rel_position) * begin_avg_note
        velocity = int(rel_position * end_melody[0].velocity + (1 - rel_position) * begin_melody[-1].velocity)
        if position + note_length > begin_of_end:
            break
        pitch = int(f(position, x_points, y_points))
        result.append(ct.Note(start=int(position), end=int(position+note_length), pitch=int(pitch), velocity=int(velocity)))
        position += note_length + 20

    # Add end to result
    for note in end_notes:
        note.start += begin_of_end
        note.end += begin_of_end
    result.extend(end_notes)

    write_midi(outfile, result)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='')

    parser.add_argument('--begin', type=Path, default="end_orig.mid")
    parser.add_argument('--end', type=Path, default="begin_orig.mid")
    parser.add_argument('--outfile', type=Path, default='result.mid')
    parser.add_argument('--length', type=int, default=4)

    args = parser.parse_args()

    main(args.begin, args.end, args.length, args.outfile)
