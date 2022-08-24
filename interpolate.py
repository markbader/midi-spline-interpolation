from typing import List
from scipy import interpolate
import argparse
from pathlib import Path

from music21 import converter, note, chord, stream, midi, interval, pitch, harmony

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

        self.stream = input_stream.transpose(target_interval)

    def extract_musical_features(self) -> None:
        bar_length = self.stream.timeSignature.barDuration.quarterLength
        num_bars = self.stream.duration.quarterLength // bar_length
        num_notes = 0
        polyphony = 0
        velocity = 0
        avg_pitch = 0
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

        self.notes_per_bar = round(num_notes / num_bars)
        self.polyphony = round(polyphony / num_notes)
        self.velocity = round(velocity / num_notes)
        self.avg_pitch = round(avg_pitch / polyphony)

    def extract_melody(self, number: int) -> stream.Stream:
        melody = stream.Stream()

        for element in self.stream:
            if isinstance(element, chord.Chord):
                melody.append(note.Note(pitchName=element.notes[number].pitch, offset=element.offset, duration=element.duration))
            elif isinstance(element, note.Note):
                melody.append(element)
        return melody

class MidiInterpolator:
    def __init__(self, files: List[Path], length: int, outfile: Path):
        self.filenames = files
        self.transition_length = length
        self.outfile = outfile

        self.main()

    def main(self) -> None:
        self.output_stream = stream.Stream()

        self.read_notes()

        # Combine all streams and their transitions to a single stream
        for i in range(len(self.streams) - 1):
            self.current_stream = MusicalFeatures(self.streams[i])
            self.next_stream = MusicalFeatures(self.streams[i + 1])

            self.output_stream.append(self.current_stream.stream)

            self.generate_transition()

        self.output_stream.append(self.next_stream.stream)

        self.output_stream.write('midi', self.outfile)

    def read_notes(self) -> None:
        self.streams = []

        for filepath in self.filenames:
            file = converter.parse(filepath)
            self.streams.append(file.flatten())

    def calc(self, param: str, bar_nr: int) -> int:
        rel_position = bar_nr / (self.transition_length + 1)
        return round(rel_position * getattr(self.next_stream, param) + (1 - rel_position) * getattr(self.current_stream, param))

    def generate_transition(self):
        interpolation_curves = self.generate_interpolation_curves()
        for bar_nr in range(1, self.transition_length + 1):
            num_notes = self.calc('notes_per_bar', bar_nr)
            polyphony = self.calc('polyphony', bar_nr)
            velocity = self.calc('velocity', bar_nr)
            duration = 4 / num_notes
            for _ in range(num_notes):
                offset = self.output_stream.duration.quarterLength
                if polyphony <= 1:
                    # interpolate pitch from spline function and map it to white key
                    interpolated_melody = 0
                    melody1 = int(interpolate.splev(4.0 - float(offset), interpolation_curves[0])) - self.current_stream.avg_pitch
                    melody2 = int(interpolate.splev(4.0 - float(offset), interpolation_curves[0])) - self.current_stream.avg_pitch

                    note_pitch = int(interpolate.splev(float(offset), interpolation_curves[0])) + interpolated_melody
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
                        pitch = int(interpolate.splev(float(offset), interpolation_curves[i]))
                        white = [0, 2, 4, 5, 7, 9, 11]
                        if pitch % 12 not in white:
                            pitch += 1

                        newNote = note.Note(pitch)
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
            begin_melody = self.current_stream.melodies[min(i, len(self.current_stream.melodies) - 1)]
            end_melody = self.next_stream.melodies[min(i, len(self.next_stream.melodies) - 1)]

            x_points, y_points = [], []

            bar_length = self.current_stream.stream.timeSignature.barDuration.quarterLength

            for note in begin_melody:
                x_points.append(note.offset)
                y_points.append(note.pitch.midi)

            end_of_begin = 0.0 if not begin_melody.last() else begin_melody.last().offset + begin_melody.last().duration.quarterLength
            space = self.transition_length * bar_length
            begin_of_end = end_of_begin + space

            for note in end_melody:
                x_points.append(note.offset + begin_of_end)
                y_points.append(note.pitch.midi)

            curves.append(interpolate.splrep(x_points, y_points, s=12))
        return curves

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='')

    parser.add_argument('--files', type=Path, nargs='+', default=["begin_orig.mid", "end_orig.mid"])
    parser.add_argument('--outfile', type=Path, default='result.mid')
    parser.add_argument('--length', type=int, default=4)

    args = parser.parse_args()

    MidiInterpolator(args.files, args.length, args.outfile)
