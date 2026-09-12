# Setup Guide: HanaSim + pyhanabi (IntAI) for Windows (WSL)

This guide takes you from a clean Windows machine to running Hanabi games with our AI agents. It puts together instructions that were previously scattered across repos and messages.

**The big picture:** our simulator (`pyhanabi`) uses a C++ game engine (`HanaSim`) through a Python binding. The engine's build tools (`cmake`, `make`, `gcc`) are Linux tools, so on Windows we work inside **WSL** (Windows Subsystem for Linux). 

Setup then has three parts: build the binding from HanaSim, set up pyhanabi, and connect the two by copying the binding into pyhanabi's environment.

---

## 0. Install WSL (If you haven't)
From now on, **run every command in this guide inside the Ubuntu terminal**

---

## 1. Prerequisites (inside Ubuntu)

Install the C++ build toolchain and git:

```sh
sudo apt update
sudo apt install -y git cmake make gcc g++
```

Install **[uv](https://docs.astral.sh/uv/)** — the Python environment manager we use:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then close and reopen the Ubuntu terminal so `uv` is on your PATH.

*What this does: installs the compiler toolchain needed to build the C++ engine, and the tool we use to create consistent Python environments.*

---

## 2. Build the HanaSim Python binding

### 2.1 Clone HanaSim on the `pyhanabi-xp` branch

```sh
cd ~
git clone --branch pyhanabi-xp https://github.com/UofT-Hanabi-Lab/HanaSim.git
cd HanaSim
```

*What this does: gets the C++ game engine. The `pyhanabi-xp` branch is the one that exposes the engine to Python via pybind11.*

### 2.2 Create a Python 3.12 environment and install build packages

```sh
uv venv -p 3.12
source .venv/bin/activate
uv pip install "pybind11[global]" numpy gymnasium
```

*What this does: creates an isolated Python 3.12 environment and installs the packages needed to compile the binding. **The Python version matters** — the binding only works with the exact Python version it was built against, and pyhanabi requires 3.12.*

### 2.3 Compile

With the environment from 2.2 still active:

```sh
mkdir build
cd build
cmake -DPython3_EXECUTABLE=$(which python) ..
make
```

This produces a file named like `hana_sim.cpython-312-x86_64-linux-gnu.so` in the `build/` directory. You'll copy it in step 4.

*What this does: compiles the C++ engine into a shared library (`.so` file) that Python can import as a module. The `-DPython3_EXECUTABLE` flag pins the build to the 3.12 environment you just created.*

---

## 3. Set up pyhanabi (IntAI)

### 3.1 Clone pyhanabi on the `hanabilive_converter` branch

```sh
cd ~
git clone --branch hanabilive_converter https://github.com/UofT-Hanabi-Lab/pyhanabi.git
cd pyhanabi
```

*What this does: gets our simulator and agent framework. `hanabilive_converter` is the branch we actively develop on.*

### 3.2 Create the environment and install dependencies

```sh
uv venv -p 3.12
uv sync
```

*What this does: creates pyhanabi's own Python 3.12 environment and installs all dependencies pinned in `pyproject.toml` / `uv.lock`, so everyone in the group runs identical package versions.*

---

## 4. Connect the two: install the binding into pyhanabi

Copy the `.so` file built in step 2.3 into pyhanabi's environment, renaming it to `hana_sim.so`:

```sh
cp ~/HanaSim/build/hana_sim.cpython-312-*.so ~/pyhanabi/.venv/lib/python3.12/site-packages/hana_sim.so
```

*What this does: places the compiled engine where pyhanabi's Python can find it, so `import hana_sim` works. Without this file, nothing in pyhanabi will run.*

---

## 5. Verify your setup by running games

Activate the pyhanabi environment first:

```sh
cd ~/pyhanabi
source .venv/bin/activate
```

**Command line** — run a full AI-vs-AI game:

```sh
python hanabi.py full full full
```

This plays one 3-player game between three intentional agents and prints the result. See `player_types` in `hanabi.py` for all valid AI names (`random`, `inner`, `outer`, `full`, `case`, ...).

**Graphical interface** — play in your browser:

```sh
python httpui.py
```

Then open <http://127.0.0.1:31337/> in your **normal Windows browser** — WSL forwards localhost automatically. Use the GUI for playing games yourself and for development/debugging; use the command line for batch AI-vs-AI simulations.

**If both of these work, your setup is complete.** 🎉

---

## 6. Optional: pre-commit hooks

Do this if you'll push code:

```sh
uv run pre-commit install
```

*What this does: auto-runs our linters (ruff, mypy) on each commit to keep code quality consistent.*

---

## Troubleshooting

- **`wsl --install` does nothing or errors** — make sure PowerShell is running as Administrator, and that virtualization is enabled in your BIOS (usually on by default). Then try `wsl --update`.
- **`ModuleNotFoundError: No module named 'hana_sim'`** — the binding isn't in pyhanabi's site-packages (step 4), or it was built with a different Python version than 3.12 (step 2.2).
- **`cmake` can't find pybind11** — make sure the HanaSim venv was active when you ran `cmake`, and that you installed `pybind11[global]` (the `[global]` part matters — it installs the CMake config files).
- **Build is extremely slow or fails with permission errors** — your repos are probably under `/mnt/c/`. Move them into the Linux home directory (`~`) and rebuild.
- **`uv: command not found` after installing** — close and reopen the Ubuntu terminal, or run `source ~/.bashrc`.
