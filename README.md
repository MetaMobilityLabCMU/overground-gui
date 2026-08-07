# Overground GUI

Standalone coordinate-cue GUI for overground walking trials.

## Conda environment

```bash
cd overground_gui
conda env create -f environment.yml
conda activate jinwoo-gui
```

Update an existing env:

```bash
conda env update -f environment.yml --prune
```

## Run (standalone)

After the env is created/activated, any of:

```bash
overground-gui
python -m overground_gui
./run_overground_gui.sh
```

`run_overground_gui.sh` activates `jinwoo-gui` automatically if needed.
