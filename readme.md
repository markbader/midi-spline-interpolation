# Music transition generation with cubic spline function

This comand line script takes two MIDI files as Input and generates a transition based on a calculated cubic spline function.

## Installation
```
git clone git@github.com:markbader/midi-spline-interpolation
cd  midi-spline-interpolation
pip install -r requirement.txt
```

## Run the script
```
python3 interpolate.py --begin begin_orig.mid --end end_orig.mid --length 3
```
