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
    tck = interpolate.splrep(x_points, y_points, s=25)
    return interpolate.splev(x, tck)

def nearest_note_length(aprox_note_length):
    assert quarter_length != None, 'Quarter length not defined.'
    note_lenghts = [quarter_length // 4, quarter_length // 2, quarter_length, quarter_length * 2, quarter_length * 4]
    nearest = quarter_length
    for length in note_lenghts:
        if abs(length - aprox_note_length) < abs(nearest - aprox_note_length):
            nearest = length
    return nearest

def nearest_start(aprox_note_start):
    assert quarter_length != None, 'Quarter length not defined.'
    note_lenghts = [quarter_length * 4, quarter_length * 2, quarter_length, quarter_length // 2]
    nearest = 0
    for length in note_lenghts:
        position = (aprox_note_start // length) * length
        nearest += position
        aprox_note_start -= position
    return nearest


def main(begin: Path, end: Path, length: int, outfile: Path) -> None:
    begin_notes = read_notes(begin)
    end_notes = read_notes(end)

    begin_bars = begin_notes[-1].start // bar_length + 1
    end_bars = end_notes[-1].start // bar_length + 1

    begin_melody = extract_melody(begin_notes)
    end_melody = extract_melody(end_notes)

    result = []

    # Calculate points to generate curve
    x_points = []
    y_points = []

    begin_note_count = 0
    for note in begin_melody:
        x_points.append(int(note.start))
        y_points.append(int(note.pitch))
        bar_nr = note.start // bar_length
        if bar_nr == begin_bars - 1:
            begin_note_count += 1

    end_of_begin = begin_melody[-1].end
    space = length * quarter_length * 4
    begin_of_end = end_of_begin + space

    x_points.append(end_of_begin+space//2)
    y_points.append((y_points[-1] + end_melody[0].pitch)//2)

    end_note_count = 0
    for note in end_melody:
        x_points.append(int(note.start) + begin_of_end)
        y_points.append(int(note.pitch))
        bar_nr = note.start // bar_length
        if bar_nr == 0:
            end_note_count += 1


    # Analyze note length, beats and velocity
    notes_end_of_begin = {}
    for note in begin_notes:
        bar_nr = note.start // bar_length
        if bar_nr != begin_bars - 1:
            continue
        notes_end_of_begin[note.start % bar_length] = [int(note.end - note.start), note.velocity]

    notes_begin_of_end = {}
    for note in end_notes:
        note.start += begin_of_end
        note.end += begin_of_end

        bar_nr = note.start // bar_length
        if bar_nr != begin_bars + length + end_bars - 1:
            continue
        notes_begin_of_end[note.start % bar_length] = [int(note.end - note.start), note.velocity]

    # Combine begin, generated transition and end to a single stream of notes
    result.extend(begin_notes)

    # Create transition
    for bar_nr in range(1, length + 1):
        rel_position = bar_nr / (length + 1)
        num_notes = int(rel_position * end_note_count + (1 - rel_position) * begin_note_count)

        # calculate for each note how long it should be
        for i in range(num_notes):
            current_interval = range(i * bar_length // num_notes, (i + 1) * bar_length // num_notes)
            avg_start_begin = 0
            avg_length_begin = 0
            avg_velocity_begin = 0
            counter = 0
            for time, note in notes_end_of_begin.items():
                note_interval = range(time, time + note[0])
                if bool(set(note_interval).intersection(current_interval)):
                    avg_start_begin += time
                    avg_length_begin += note[0]
                    avg_velocity_begin += note[1]
                    counter += 1
            if counter:
                avg_start_begin //= counter
                avg_length_begin //= counter
                avg_velocity_begin //= counter

            avg_start_end = 0
            avg_length_end = 0
            avg_velocity_end = 0
            counter = 0
            for time, note in notes_begin_of_end.items():
                note_interval = range(time, time + note[0])
                if bool(set(note_interval).intersection(current_interval)):
                    avg_start_end += time
                    avg_length_end += note[0]
                    avg_velocity_end += note[1]
                    counter += 1
            if counter:
                avg_start_end //= counter
                avg_length_end //= counter
                avg_velocity_end //= counter

            aprox_note_start = int(rel_position * avg_start_end + (1 - rel_position) * avg_start_begin)
            aprox_note_length = int(rel_position * avg_length_end + (1 - rel_position) * avg_length_begin)
            aprox_note_velocity = int(rel_position * avg_velocity_end + (1 - rel_position) * avg_velocity_begin)

            # map aproximated values to actual note lengths
            note_length = nearest_note_length(aprox_note_length)
            note_start = nearest_start(aprox_note_start) + (begin_bars + bar_nr - 1) * bar_length
            note_pitch = int(f(note_start + note_length//2, x_points, y_points))

            result.append(ct.Note(int(aprox_note_velocity), int(note_pitch), int(note_start), int(note_start + note_length)))

    result.extend(end_notes)

    write_midi(outfile, result)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='')

    parser.add_argument('--begin', type=Path, default="begin_orig.mid")
    parser.add_argument('--end', type=Path, default="end_orig.mid")
    parser.add_argument('--outfile', type=Path, default='result.mid')
    parser.add_argument('--length', type=int, default=4)

    args = parser.parse_args()

    main(args.begin, args.end, args.length, args.outfile)
