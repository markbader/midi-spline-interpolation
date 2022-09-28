from typing import List
from scipy import interpolate
import argparse
from pathlib import Path
# import numpy as np

# import matplotlib.pyplot as plt

from music21 import converter, note, chord, stream, interval, pitch, tempo, key

class MusicalFeatures:
    def __init__(self, input_stream):
        self.init_stream(input_stream)

        self.extract_musical_features()
        self.melodies = [self.extract_melody(i) for i in range(self.polyphony)]

    def init_stream(self, input_stream: stream.Stream) -> None:
        '''Load input stream to self.stream and transpose it to a keyset with only white keys'''
        key = input_stream.analyze('key')

        if key.mode == "major":
            target_interval = interval.Interval(key.tonic, pitch.Pitch('C'))

        else:
            target_interval = interval.Interval(key.tonic, pitch.Pitch('A'))

        self.stream: stream.Stream = input_stream.transpose(target_interval).flatten()

    def extract_musical_features(self) -> None:
        self.bar_length = self.stream.timeSignature.barDuration.quarterLength
        self.num_bars = self.stream.duration.quarterLength // self.bar_length
        self.length = self.stream.duration.quarterLength
        num_notes = 0
        polyphony = 0
        velocity = 0
        avg_pitch = 0
        avg_tempo = None
        self.first_bar = stream.Stream()
        self.last_bar = stream.Stream()
        for element in self.stream:
            if isinstance(element, note.Note):
                num_notes += 1
                polyphony += 1
                velocity += element.volume.velocity
                avg_pitch += element.pitch.midi
            if isinstance(element, chord.Chord):
                num_notes += 1
                polyphony += len(element.notes)
                velocity += element.volume.velocity
                for n in element.notes:
                    avg_pitch += n.pitch.midi
            if isinstance(element, tempo.MetronomeMark):
                avg_tempo = element.number
        if not avg_tempo:
            avg_tempo = 120 # use 120 BPM as a default tempo
        
        self.notes_per_bar = round(num_notes / self.num_bars)
        self.avg_tempo = avg_tempo
        self.polyphony = round(polyphony / num_notes)
        self.velocity = round(velocity / num_notes)
        self.avg_pitch = round(avg_pitch / polyphony)

    def extract_melody(self, number: int) -> stream.Stream:
        melody = stream.Stream()
        last_note = None

        for element in self.stream:
            if isinstance(element, chord.Chord):
                melody.append(note.Note(pitchName=element.notes[min(number, len(element.notes) - 1)].pitch, offset=element.offset, duration=element.duration))
                last_note = note.Note(pitchName=element.notes[min(number, len(element.notes) - 1)].pitch, offset=element.offset + element.duration.quarterLength)
            elif isinstance(element, note.Note):
                melody.append(element)
                last_note = note.Note(pitchName=element.pitch, offset=element.offset + element.duration.quarterLength)
        if last_note:
            melody.append(last_note)
        return melody

class MidiInterpolator:
    def __init__(self, files: List[Path]=None, length: int=4, outfile: Path=None, streams: List[stream.Stream]=None, note_variance: float=0.9):
        self.filenames = files
        self.transition_length = length
        self.outfile = outfile
        self.streams = streams
        self.note_variance_factor = note_variance

    def create_stream_infilling(self) -> stream.Stream:
        self.output_stream = stream.Stream()
        # Combine all streams and their transitions to a single stream
        for i in range(len(self.streams) - 1):
            self.current_stream = MusicalFeatures(self.streams[i])
            self.next_stream = MusicalFeatures(self.streams[i + 1])
            assert self.current_stream.bar_length == self.next_stream.bar_length, \
                "Different time signatures in given midi files, can not interpolate pieces."

            self.output_stream.append(self.current_stream.stream)

            self.generate_transition()

        self.output_stream.append(self.next_stream.stream)

        self.output_stream = self.remove_key_signatures(self.output_stream)

        return self.output_stream
    
    def create_infilling(self) -> None:
        try:
            if not self.streams:
                self.read_notes()

            self.create_stream_infilling()

            self.output_stream.write('midi', self.outfile)
        except Exception as e:
            print('Error while processing files', e)

    def remove_key_signatures(self, midi_stream):
        new_stream = midi_stream.flatten()
        for elem in new_stream:
            if isinstance(elem, key.KeySignature) or isinstance(elem, key.Key):
                elem_index = new_stream.index(elem)
                new_stream.pop(elem_index)

        return new_stream

    def read_notes(self) -> None:
        self.streams = []

        for filepath in self.filenames:
            file = converter.parse(filepath)
            self.streams.append(file.flatten())

    def calc(self, bar_nr: int, param: str=None, x1: float=None, x2: float=None) -> int:
        rel_position = bar_nr / (self.transition_length + 1)
        if param:
            x1 = getattr(self.current_stream, param)
            x2 = getattr(self.next_stream, param)
        if x1 != None and x2 != None:
            return round(rel_position * x2 + (1 - rel_position) * x1)
    
    def clamp_to_pitch(self, number) -> int:
        return max(10, min(117, int(number)))

    def generate_transition(self):
        interpolation_curves = self.generate_interpolation_curves()
        duration1 = self.current_stream.length
        duration2 = self.next_stream.length
        start2 = duration1 + self.transition_length * self.current_stream.bar_length

        for bar_nr in range(1, self.transition_length + 1):
            num_notes = self.calc(bar_nr, param='notes_per_bar')
            polyphony = self.calc(bar_nr, param='polyphony')
            velocity = self.calc(bar_nr, param='velocity')
            avg_tempo = self.calc(bar_nr, param='avg_tempo')
            duration = self.current_stream.bar_length / num_notes
            self.output_stream.append(tempo.MetronomeMark(number=avg_tempo))
            for _ in range(num_notes):
                offset = self.output_stream.duration.quarterLength
                position1 = offset % duration1
                position2 = start2 + (start2 + offset) % duration2
                if polyphony <= 1:
                    # interpolate pitch from spline function and map it to white key
                    melody1 = round((interpolate.splev(position1, interpolation_curves[0]) - self.current_stream.avg_pitch) * self.note_variance_factor)
                    melody2 = round((interpolate.splev(position2, interpolation_curves[0]) - self.next_stream.avg_pitch) * self.note_variance_factor)
                    interpolated_melody = self.calc(bar_nr, x1=melody1, x2=melody2)

                    note_pitch = self.clamp_to_pitch(interpolate.splev(float(offset), interpolation_curves[0]) + interpolated_melody)
                    white = [0,2,4,5,7,9,11]
                    if note_pitch % 12 not in white:
                        note_pitch += 1

                    newNote = note.Note(note_pitch)
                    newNote.volume.velocity = velocity
                    newNote.duration.quarterLength = duration
                    self.output_stream.append(newNote)
                else:
                    newChord = chord.Chord()
                    for i in range(polyphony):
                        # interpolate pitch from spline function and map it to white key
                        melody1 = round((interpolate.splev(position1, interpolation_curves[i]) - self.current_stream.avg_pitch) * self.note_variance_factor)
                        melody2 = round((interpolate.splev(position2, interpolation_curves[i]) - self.next_stream.avg_pitch) * self.note_variance_factor)
                        interpolated_melody = self.calc(bar_nr, x1=melody1, x2=melody2)
                        note_pitch = self.clamp_to_pitch(interpolate.splev(float(offset), interpolation_curves[i]) + interpolated_melody)
                        white = [0, 2, 4, 5, 7, 9, 11]
                        if note_pitch % 12 not in white:
                            note_pitch += 1

                        newNote = note.Note(note_pitch)
                        newNote.volume.velocity = velocity
                        newNote.duration.quarterLength = duration
                        newChord.add(newNote)
                    newChord.volume.velocity = velocity
                    newChord.duration.quarterLength = duration
                    self.output_stream.append(newChord)


    def generate_interpolation_curves(self):
        max_polyphony = max(self.current_stream.polyphony, self.next_stream.polyphony)
        curves = []
        for i in range(max_polyphony):
            # fig, ax = plt.subplots(figsize=(12, 4))
            # xs = np.arange(0.0, 45.0, 0.1)
            begin_melody = self.current_stream.melodies[min(i, len(self.current_stream.melodies) - 1)]
            end_melody = self.next_stream.melodies[min(i, len(self.next_stream.melodies) - 1)]

            x_points, y_points = [], []

            bar_length = self.current_stream.bar_length

            for note in begin_melody:
                x_points.append(note.offset)
                y_points.append(note.pitch.midi)

            end_of_begin = self.current_stream.length
            space = self.transition_length * bar_length
            begin_of_end = end_of_begin + space

            for note in end_melody:
                x_points.append(note.offset + begin_of_end)
                y_points.append(note.pitch.midi)

            curves.append(interpolate.splrep(x_points, y_points, s=35))
            # ax.plot(x_points, y_points, 'o')
            # ax.plot(xs, interpolate.splev(xs, curves[-1]))
            # plt.show()
        return curves

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='')

    parser.add_argument(
        '--files', 
        type=Path, 
        nargs='+', 
        default=["begin_orig.mid", "end_orig.mid"])

    parser.add_argument(
        '--outfile', 
        type=Path, 
        default='result.mid')

    parser.add_argument(
        '--length', 
        type=int, 
        default=7)

    parser.add_argument(
        '--note_variance', 
        type=float, 
        default=0.9)

    args = parser.parse_args()

    midi_interpolator = MidiInterpolator(
        files=args.files, length=args.length, 
        outfile=args.outfile, note_variance=args.note_variance)
    midi_interpolator.create_infilling()
    
