from typing import List
from scipy import interpolate
import argparse
from pathlib import Path

from miditoolkit.midi import parser as mid_parser
from miditoolkit.midi import containers as ct

quarter_length = None
bar_length = None
time_signature = None

def read_notes(filepath: Path, track: int=0) -> List:
    global quarter_length
    global bar_length
    global time_signature

    # load midi file
    mido_obj = mid_parser.MidiFile(filepath)
    if not quarter_length:
        quarter_length = mido_obj.ticks_per_beat
    else:
        assert quarter_length == mido_obj.ticks_per_beat, 'Begin and end file have different sample rates.'

    assert len(mido_obj.time_signature_changes) == 1, f'{filepath} has more than one time signature change event.{mido_obj.time_signature_changes}'

    if not time_signature:
        time_signature = mido_obj.time_signature_changes[0]
    else:
        assert time_signature.numerator == mido_obj.time_signature_changes[0].numerator, f'No matching numerator in time signature between begin und end.'
        assert time_signature.denominator == mido_obj.time_signature_changes[0].denominator, f'No matching denominator in time signature between begin und end.'
    bar_length = quarter_length * 4 * time_signature.numerator // time_signature.denominator

    return mido_obj.instruments[track].notes

def extract_melody(notes):
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

    return melody

def write_midi(filepath: Path, notes):
    # create an empty file
    mido_obj = mid_parser.MidiFile()
    mido_obj.ticks_per_beat = quarter_length

    # create an  instrument
    track = ct.Instrument(program=0, is_drum=False, name='piano track')
    mido_obj.instruments = [track]

    mido_obj.instruments[0].notes = notes

    # write to file
    mido_obj.dump(filepath)

def f(x: float, x_points, y_points):
    tck = interpolate.splrep(x_points, y_points, s=35)
    return interpolate.splev(x, tck)

def get_closest_note(notes, idx, num_notes):
    # TODO: define better function to approximate note calculation
    rel_time = idx/num_notes
    #print(notes)
    derivation = []
    for time in notes:
        derivation.extend([time]*notes[time][0])
    best_time = derivation[int(len(derivation) * rel_time)]
    return [best_time, notes[best_time][0], notes[best_time][1]]
    print(derivation)
    current_min = list(notes.keys())[0]
    for time in notes:
        if abs(time - rel_time) < abs(current_min - rel_time):
            current_min = time
    return [current_min, notes[current_min][0], notes[current_min][1]]


def main(begin: Path, end: Path, length: int, outfile: Path) -> None:
    begin_notes = read_notes(begin)
    end_notes = read_notes(end)

    begin_melody = extract_melody(begin_notes)
    end_melody = extract_melody(end_notes)

    result = []

    # Calculate points to generate curve
    x_points = []
    y_points = []

    for note in begin_melody:
        x_points.append(int(note.start))
        y_points.append(int(note.pitch))

    end_of_begin = begin_melody[-1].end
    space = length * quarter_length * 4
    begin_of_end = end_of_begin + space

    for note in end_melody:
        x_points.append(int(note.start) + begin_of_end)
        y_points.append(int(note.pitch))


    # Analyze note length, beats and velocity
    notes_end_of_begin = {}
    begin_bars = begin_notes[-1].start // bar_length + 1
    for note in begin_notes:
        bar_nr = note.start // bar_length
        if bar_nr != begin_bars - 1:
            continue
        notes_end_of_begin[note.start % bar_length] = [int(note.end - note.start), note.velocity]

    notes_begin_of_end = {}
    end_bars = end_notes[-1].start // bar_length + 1
    for note in end_notes:
        note.start += begin_of_end
        note.end += begin_of_end

        bar_nr = note.start // bar_length
        if bar_nr != begin_bars + length + end_bars - 1:
            continue
        notes_begin_of_end[note.start % bar_length] = [int(note.end - note.start), note.velocity]

    # Combine begin, generated transition and end to a single stream of notes
    result.extend(begin_notes)

    print(begin_bars)
    print(end_bars)
    # Create transition
    for bar_nr in range(1, length + 1):
        rel_position = bar_nr / (length + 1)
        num_notes = int(rel_position * len(notes_begin_of_end) + (1 - rel_position) * len(notes_end_of_begin))
        for i in range(num_notes):
            close_begin_note = get_closest_note(notes_end_of_begin, i, num_notes)
            close_end_note = get_closest_note(notes_begin_of_end, i, num_notes)
            note_start = (begin_bars + bar_nr - 1) * bar_length + rel_position * close_end_note[0] + (1 - rel_position) * close_begin_note[0]
            note_length = rel_position * close_end_note[1] + (1 - rel_position) * close_begin_note[1]
            note_velocity = rel_position * close_end_note[2] + (1 - rel_position) * close_begin_note[2]
            note_pitch = int(f(note_start, x_points, y_points))
            result.append(ct.Note(int(note_velocity), int(note_pitch), int(note_start), int(note_start + note_length)))

    result.extend(end_notes)

    write_midi(outfile, result)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='')

    parser.add_argument('--begin', type=Path, default="begin_orig.mid")
    parser.add_argument('--end', type=Path, default="end_orig.mid")
    parser.add_argument('--outfile', type=Path, default='result3.mid')
    parser.add_argument('--length', type=int, default=8)

    args = parser.parse_args()

    main(args.begin, args.end, args.length, args.outfile)
