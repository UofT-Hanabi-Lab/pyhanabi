# Setup Guide: HanaSim + pyhanabi (IntAI) for Windows (WSL)

This guide takes you from a clean Windows machine to running Hanabi games with our AI agents. It puts together instructions that were previously scattered across repos and messages.

**The big picture:** our simulator (`pyhanabi`) uses a C++ game engine (`HanaSim`) through a Python binding. The engine's build tools (`cmake`, `make`, `gcc`) are Linux tools, so on Windows we work inside **WSL** (Windows Subsystem for Linux). 

Setup then has three parts: build the binding from HanaSim, set up pyhanabi, and connect the two by copying the binding into pyhanabi's environment.

---

## 0. Install WSL (If you haven't)

Open **PowerShell as Administrator** and run:

```powershell
wsl --install
```

Restart your computer when prompted. On first launch, Ubuntu will ask you to create a Linux username and password (this password is what `sudo` asks for later).

From now on, **run every command in this guide inside the Ubuntu terminal** (search "Ubuntu" in the Start menu).

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

### 2.1 Clone HanaSim on the `expose-deck` branch

```sh
cd ~
git clone --branch expose-deck https://github.com/UofT-Hanabi-Lab/HanaSim.git
cd HanaSim
```

*What this does: gets the C++ game engine. The `expose-deck` branch contains the Python binding **plus** the deck-exposure feature our game logging and agents depend on 

Do not use older branches like `pyhanabi-xp`, which build a binding missing that feature.*

> **Want the repo somewhere else?** Append the target path to the clone command, e.g. `git clone --branch expose-deck https://github.com/UofT-Hanabi-Lab/HanaSim.git ~/repos/HanaSim`. If you do, use your own paths in place of `~/HanaSim` and `~/pyhanabi` in steps 4–5.

### 2.2 Create a Python 3.12 environment and install build packages

```sh
uv venv -p 3.12
source .venv/bin/activate
uv pip install "pybind11[global]" numpy gymnasium
```

What this does: creates an isolated Python 3.12 environment and installs the packages needed to compile the binding. 

**The Python version matters:** the binding only works with the exact Python version it was built against, and pyhanabi requires 3.12.

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

*What this does: gets our simulator and agent framework.*

> **Important: `hanabilive_converter` is the branch we actively develop on.** All current work lives here, not on `main`. Make sure you are on this branch before reading code, running experiments, or pushing changes.

> **Want the repo somewhere else?** Same as in step 2.1: append the target path to the clone command, and use your own paths in steps 4–5.

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

We have also implemented variants of the full agent during the summer. Run variant nunber $x$ by appending "\x" after "full".
```sh
python hanabi.py full/5 full/5 full/5
```

**Graphical interface**:

```sh
python httpui.py
```

Then open <http://127.0.0.1:31337/> in your browser. 

Use the GUI for playing games yourself and for development/debugging; use the command line for batch AI-vs-AI simulations.

**If both of these work, your setup is complete!**
